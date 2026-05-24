# Version: 03.09.14
# Phase: PHASE2
import json
import os
import struct
import sys
import tempfile
import threading
import time
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import patch

from core.runtime import config
from core.audio.media_processor import VideoProcessor
from core.audio.stt_quality_presets import apply_stt_quality_preset


class MediaProcessorOverlapTests(unittest.TestCase):
    def setUp(self):
        self.processor = VideoProcessor()

    def _write_silent_wav(self, path: str, *, sample_rate: int = 16000, frames: int = 16000):
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(b"\x00\x00" * int(frames))

    def test_split_range_uses_real_overlap_between_chunks(self):
        chunks = self.processor._split_range_with_overlap(0.0, 80.0, max_chunk_dur=30.0, overlap_sec=3.0)

        self.assertEqual(chunks, [
            {"start": 0.0, "end": 30.0},
            {"start": 27.0, "end": 57.0},
            {"start": 54.0, "end": 80.0},
        ])

    def test_scan_transcribe_chunks_uses_shared_manifest(self):
        with tempfile.TemporaryDirectory() as chunk_dir:
            self._write_silent_wav(os.path.join(chunk_dir, "vad_010_2.000.wav"), frames=8000)
            self._write_silent_wav(os.path.join(chunk_dir, "vad_000_0.000.wav"), frames=16000)

            chunks, items, total_sec = self.processor._scan_transcribe_chunks(chunk_dir)

        self.assertEqual(chunks, ["vad_000_0.000.wav", "vad_010_2.000.wav"])
        self.assertEqual([round(item["ov_start_offset"], 3) for item in items], [0.0, 2.0])
        self.assertEqual([round(item["duration"], 3) for item in items], [1.0, 0.5])
        self.assertAlmostEqual(total_sec, 2.5, places=3)

    def test_audio_chunk_manifest_reuses_native_result_for_same_signature(self):
        from core.audio import audio_chunk_manifest as manifest_module

        with tempfile.TemporaryDirectory() as chunk_dir:
            wav_path = os.path.join(chunk_dir, "vad_000_0.000.wav")
            self._write_silent_wav(wav_path, frames=16000)
            rows = [
                {
                    "name": "vad_000_0.000.wav",
                    "path": wav_path,
                    "start": 0.0,
                    "duration": 1.0,
                    "end": 1.0,
                    "has_vad_start": True,
                }
            ]

            manifest_module._MANIFEST_CACHE.clear()
            try:
                with patch.object(manifest_module, "audio_chunk_manifest_via_swift", return_value=rows) as native:
                    first = manifest_module.audio_chunk_manifest(chunk_dir)
                    second = manifest_module.audio_chunk_manifest(chunk_dir)
            finally:
                manifest_module._MANIFEST_CACHE.clear()

        self.assertEqual(first, rows)
        self.assertEqual(second, rows)
        native.assert_called_once()

    def test_chunk_manifest_cache_invalidates_when_wav_changes_without_directory_mtime(self):
        with tempfile.TemporaryDirectory() as chunk_dir:
            wav_path = os.path.join(chunk_dir, "vad_000_0.000.wav")
            self._write_silent_wav(wav_path, frames=16000)
            dir_stat = os.stat(chunk_dir)

            first = self.processor._audio_chunk_manifest(chunk_dir)

            self._write_silent_wav(wav_path, frames=32000)
            next_ns = int(os.stat(wav_path).st_mtime_ns) + 1_000_000_000
            os.utime(wav_path, ns=(next_ns, next_ns))
            os.utime(chunk_dir, ns=(int(dir_stat.st_atime_ns), int(dir_stat.st_mtime_ns)))
            second = self.processor._audio_chunk_manifest(chunk_dir)

        self.assertEqual(round(first[0]["duration"], 3), 1.0)
        self.assertEqual(round(second[0]["duration"], 3), 2.0)

    def test_chunk_path_covering_time_reuses_manifest_cache(self):
        with tempfile.TemporaryDirectory() as chunk_dir:
            rows = [
                {
                    "name": "vad_000_0.000.wav",
                    "path": os.path.join(chunk_dir, "vad_000_0.000.wav"),
                    "start": 0.0,
                    "duration": 1.0,
                    "end": 1.0,
                    "has_vad_start": True,
                },
                {
                    "name": "vad_001_2.000.wav",
                    "path": os.path.join(chunk_dir, "vad_001_2.000.wav"),
                    "start": 2.0,
                    "duration": 1.0,
                    "end": 3.0,
                    "has_vad_start": True,
                },
            ]
            with patch("core.audio.media_processor_transcribe.audio_chunk_manifest", return_value=rows) as manifest:
                first = self.processor._chunk_path_covering_time(chunk_dir, 0.5)
                second = self.processor._chunk_path_covering_time(chunk_dir, 2.5)

        self.assertTrue(first.endswith("vad_000_0.000.wav"))
        self.assertTrue(second.endswith("vad_001_2.000.wav"))
        manifest.assert_called_once()

    def test_grouped_chunks_from_existing_wavs_uses_manifest_shape(self):
        with tempfile.TemporaryDirectory() as chunk_dir:
            self._write_silent_wav(os.path.join(chunk_dir, "plain.wav"), frames=16000)
            self._write_silent_wav(os.path.join(chunk_dir, "vad_002_4.000.wav"), frames=8000)
            self._write_silent_wav(os.path.join(chunk_dir, "vad_001_1.000.wav"), frames=16000)

            grouped = self.processor._grouped_chunks_from_existing_wavs(chunk_dir)

        self.assertEqual(grouped, [{"start": 1.0, "end": 2.0}, {"start": 4.0, "end": 4.5}])

    def test_release_after_transcribe_keeps_macos_persistent_worker_warm(self):
        class _LiveProc:
            def poll(self):
                return None

        proc = _LiveProc()
        self.processor._whisperkit_runner_proc = proc
        self.processor._whisper_proc = proc
        self.processor._load_all_settings = lambda: {"stt_persistent_runtime_reuse_enabled": True}

        with patch.object(config, "IS_MAC", True), \
             patch("core.performance.current_resource_snapshot", return_value={
                 "available_memory_ratio": 0.5,
                 "available_memory_bytes": 8 * 1024 ** 3,
                 "memory_pressure_stage": "normal",
             }), \
             patch.object(self.processor, "stop_transcribe") as stop_transcribe, \
             patch("core.audio.media_processor_transcribe.clear_audio_model_memory_caches") as clear_caches:
            self.processor._release_after_transcribe_job("STT1")

        stop_transcribe.assert_not_called()
        clear_caches.assert_not_called()
        self.assertIs(self.processor._whisperkit_runner_proc, proc)
        self.assertIsNone(self.processor._whisper_proc)

    def test_mac_stt1_first_pass_routes_quality_model_to_fast_native_model(self):
        settings = {
            "stt_primary_fast_native_enabled": True,
            "stt_primary_fast_native_model": config.WHISPERKIT_FAST_MODEL,
            "stt_word_timestamp_precision_pass": False,
        }

        with patch.object(config, "IS_MAC", True):
            first_pass = self.processor._mac_primary_fast_native_model(
                config.WHISPERKIT_QUALITY_MODEL,
                settings,
                log_label="STT1",
            )
            precision_pass = self.processor._mac_primary_fast_native_model(
                config.WHISPERKIT_QUALITY_MODEL,
                {**settings, "stt_word_timestamp_precision_pass": True},
                log_label="STT1",
            )
            stt2_pass = self.processor._mac_primary_fast_native_model(
                config.WHISPERKIT_QUALITY_MODEL,
                settings,
                log_label="Fast-STT2",
            )
            komix_pass = self.processor._mac_primary_fast_native_model(
                "youngouk/whisper-medium-komixv2-mlx",
                settings,
                log_label="STT1",
            )

        self.assertEqual(first_pass, config.WHISPERKIT_FAST_MODEL)
        self.assertEqual(precision_pass, config.WHISPERKIT_QUALITY_MODEL)
        self.assertEqual(stt2_pass, config.WHISPERKIT_QUALITY_MODEL)
        self.assertEqual(komix_pass, "youngouk/whisper-medium-komixv2-mlx")

    def test_word_precision_ranges_respect_audio_budget(self):
        segments = [
            {"start": 0.0, "end": 5.0, "text": "후보1", "stt_score": 40},
            {"start": 10.0, "end": 15.0, "text": "후보2", "stt_score": 20},
            {"start": 20.0, "end": 25.0, "text": "후보3", "stt_score": 30},
            {"start": 30.0, "end": 35.0, "text": "후보4", "stt_score": 10},
        ]

        ranges = self.processor._word_precision_ranges(
            segments,
            {
                "stt_word_timestamps_precision_enabled": True,
                "stt_word_timestamps_precision_threshold": 80.0,
                "stt_word_timestamps_precision_max_segments": 4,
                "stt_word_timestamps_precision_max_audio_sec": 10.0,
            },
        )

        self.assertEqual([(item.start, item.end) for item in ranges], [(10.0, 15.0), (30.0, 35.0)])

    def test_word_precision_recheck_uses_user_selected_stt1_model(self):
        segments = [{"start": 0.0, "end": 1.0, "text": "저신뢰", "stt_score": 20}]
        settings = {
            "selected_whisper_model": "mlx-community/whisper-large-v3-mlx",
            "stt_word_timestamps_mode": "selective",
            "stt_word_timestamps_default_enabled": False,
            "stt_word_timestamps_precision_enabled": True,
        }

        with tempfile.TemporaryDirectory() as chunk_dir, \
             patch.object(self.processor, "_word_precision_ranges", return_value=[SimpleNamespace(start=0.0, end=1.0)]), \
             patch.object(self.processor, "_prepare_recheck_clip", return_value={"start": 0.0, "end": 1.0}), \
             patch.object(self.processor, "_collect_transcribe_result", return_value=[]) as collect:
            result = self.processor._recheck_word_timestamps_for_precision(
                chunk_dir,
                segments,
                settings,
                [],
                "whisperkit-persistent:large-v3-v20240930_626MB",
            )

        self.assertEqual(result, segments)
        self.assertEqual(collect.call_args.args[1], "mlx-community/whisper-large-v3-mlx")
        overrides = collect.call_args.kwargs["settings_overrides"]
        self.assertFalse(overrides["runtime_backend_autotune_enabled"])
        self.assertEqual(overrides["stt_backend_policy"], "native")
        self.assertFalse(overrides["stt_primary_fast_native_enabled"])
        self.assertTrue(overrides["stt_npu_prefer_enabled"])
        self.assertTrue(overrides["whisperkit_native_auto_enabled"])

    def test_word_precision_recheck_allows_explicit_precision_model(self):
        segments = [{"start": 0.0, "end": 1.0, "text": "저신뢰", "stt_score": 20}]
        settings = {
            "selected_whisper_model": "mlx-community/whisper-large-v3-mlx",
            "stt_word_timestamps_precision_model": "whisperkit-persistent:large-v3-v20240930_turbo_632MB",
            "stt_word_timestamps_mode": "selective",
            "stt_word_timestamps_default_enabled": False,
            "stt_word_timestamps_precision_enabled": True,
        }

        with tempfile.TemporaryDirectory() as chunk_dir, \
             patch.object(self.processor, "_word_precision_ranges", return_value=[SimpleNamespace(start=0.0, end=1.0)]), \
             patch.object(self.processor, "_prepare_recheck_clip", return_value={"start": 0.0, "end": 1.0}), \
             patch.object(self.processor, "_collect_transcribe_result", return_value=[]) as collect:
            self.processor._recheck_word_timestamps_for_precision(
                chunk_dir,
                segments,
                settings,
                [],
                "whisperkit-persistent:large-v3-v20240930_626MB",
            )

        self.assertEqual(collect.call_args.args[1], "whisperkit-persistent:large-v3-v20240930_turbo_632MB")

    def test_release_after_transcribe_stops_warm_worker_under_critical_memory(self):
        class _LiveProc:
            def poll(self):
                return None

        proc = _LiveProc()
        self.processor._whisperkit_runner_proc = proc
        self.processor._whisper_proc = proc
        self.processor._load_all_settings = lambda: {"stt_persistent_runtime_reuse_enabled": True}

        with patch.object(config, "IS_MAC", True), \
             patch("core.performance.current_resource_snapshot", return_value={
                 "available_memory_ratio": 0.04,
                 "available_memory_bytes": 512 * 1024 ** 2,
                 "memory_pressure_stage": "critical",
             }), \
             patch.object(self.processor, "stop_transcribe") as stop_transcribe, \
             patch("core.audio.media_processor_transcribe.clear_audio_model_memory_caches") as clear_caches:
            self.processor._release_after_transcribe_job("STT1")

        stop_transcribe.assert_called_once()
        clear_caches.assert_called_once_with(include_gpu=True)

    def test_release_after_transcribe_clears_cpu_only_under_warning_memory(self):
        class _LiveProc:
            def poll(self):
                return None

        proc = _LiveProc()
        self.processor._whisperkit_runner_proc = proc
        self.processor._whisper_proc = proc
        self.processor._load_all_settings = lambda: {
            "stt_persistent_runtime_reuse_enabled": False,
        }

        with patch.object(config, "IS_MAC", True),              patch("core.performance.current_resource_snapshot", return_value={
                 "available_memory_ratio": 0.15,
                 "available_memory_bytes": 2048 * 1024 ** 2,
                 "memory_pressure_stage": "warning",
             }),              patch.object(self.processor, "stop_transcribe") as stop_transcribe,              patch("core.audio.media_processor_transcribe.clear_audio_model_memory_caches") as clear_caches:
            self.processor._release_after_transcribe_job("STT1")

        stop_transcribe.assert_called_once()
        clear_caches.assert_called_once_with(include_gpu=False)

    def test_audio_route_segment_hints_mark_precision_review_and_secondary_recheck(self):
        item = {"input_path": "/tmp/vad_000_0.000.wav"}
        route_hints = {
            "vad_000_0.000.wav": {
                "audio_strategy": "noisy_voice",
                "confidence": 0.61,
                "risk_level": "high",
                "precision_review": True,
                "secondary_recheck_hint": True,
            }
        }
        segments = [{"start": 0.0, "end": 1.2, "text": "테스트"}]

        updated = self.processor._apply_audio_route_segment_hints(segments, item, route_hints)

        self.assertTrue(updated[0]["precision_review"])
        self.assertTrue(updated[0]["needs_review"])
        self.assertTrue(updated[0]["stt_route_secondary_recheck_hint"])
        self.assertEqual(updated[0]["asr_metadata"]["adaptive_audio_route"]["strategy"], "noisy_voice")

    def test_window_chunk_dir_copies_matching_audio_route_rows(self):
        with tempfile.TemporaryDirectory() as chunk_dir:
            wav_path = os.path.join(chunk_dir, "vad_000_0.000.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00\x00" * 1600)
            with open(os.path.join(chunk_dir, "audio_routes.json"), "w", encoding="utf-8") as handle:
                json.dump(
                    [
                        {"path": wav_path, "audio_strategy": "clean_voice"},
                        {"path": os.path.join(chunk_dir, "vad_001_10.000.wav"), "audio_strategy": "noisy_voice"},
                    ],
                    handle,
                    ensure_ascii=False,
                    indent=2,
                )

            window_dir = self.processor._build_window_chunk_dir(
                chunk_dir,
                [{"input_path": wav_path}],
                window_index=0,
                total_windows=1,
                window_range={"start": 0.0, "end": 10.0},
                vad_segments=[],
            )
            with open(os.path.join(window_dir, "audio_routes.json"), "r", encoding="utf-8") as handle:
                rows = json.load(handle)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["audio_strategy"], "clean_voice")

    def test_window_chunk_dir_clips_boundary_wav_to_window_range(self):
        with tempfile.TemporaryDirectory() as chunk_dir:
            wav_path = os.path.join(chunk_dir, "vad_000_0.000.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(10)
                wf.writeframes(struct.pack("<" + "h" * 100, *range(100)))

            window_dir = self.processor._build_window_chunk_dir(
                chunk_dir,
                [{"idx": 0, "input_path": wav_path, "ov_start_offset": 0.0, "duration": 10.0}],
                window_index=0,
                total_windows=1,
                window_range={"start": 2.0, "end": 5.0},
                vad_segments=[],
            )
            clipped_path = os.path.join(window_dir, "vad_000_2.000.wav")

            with wave.open(clipped_path, "rb") as clipped:
                self.assertEqual(clipped.getframerate(), 10)
                self.assertEqual(clipped.getnframes(), 30)
                frames = clipped.readframes(30)
            samples = struct.unpack("<" + "h" * 30, frames)

        self.assertEqual(samples[0], 20)
        self.assertEqual(samples[-1], 49)

    def test_native_batch_refine_routes_precision_rechecks_after_full_stt1_pass(self):
        with tempfile.TemporaryDirectory() as chunk_dir:
            for idx, start in enumerate((0.0, 2.0)):
                wav_path = os.path.join(chunk_dir, f"vad_{idx:03d}_{start:.3f}.wav")
                with wave.open(wav_path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(b"\x00\x00" * 16000)

            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "primary-native",
                "selected_whisper_model_secondary": "secondary-native",
                "runtime_backend_autotune_enabled": False,
                "stt_backend_policy": "quality",
                "stt_ensemble_enabled": False,
                "stt_native_batch_refine_enabled": True,
                "stt_word_timestamps_mode": "selective",
                "stt_word_timestamps_default_enabled": False,
                "stt_word_timestamps_precision_enabled": True,
                "stt_persistent_runtime_reuse_enabled": False,
            }

            batched_result = [([{"start": 0.0, "end": 1.0, "text": "배치 완료"}], 1, 1)]
            with patch.object(config, "IS_MAC", True), \
                 patch.object(self.processor, "_transcribe_selective_ensemble", return_value=iter(batched_result)) as batch:
                rows = list(self.processor.transcribe(chunk_dir, cleanup_chunk_dir=False))

        self.assertEqual(rows, batched_result)
        self.assertEqual(batch.call_args.kwargs["primary_model"], "primary-native")
        self.assertEqual(batch.call_args.kwargs["secondary_model"], "secondary-native")

    def test_native_batch_refine_can_be_disabled_for_streaming_chunks(self):
        settings = {
            "stt_native_batch_refine_enabled": False,
            "stt_ensemble_enabled": False,
            "stt_word_timestamps_mode": "selective",
            "stt_word_timestamps_default_enabled": False,
            "stt_word_timestamps_precision_enabled": True,
        }

        with patch.object(config, "IS_MAC", True):
            requested = self.processor._native_batch_refine_requested(
                settings,
                "primary-native",
                model_override=None,
                total_chunks=2,
            )

        self.assertFalse(requested)

    def test_build_grouped_chunks_applies_overlap_to_long_vad_sector(self):
        chunks = self.processor._build_grouped_chunks(
            [{"start": 10.0, "end": 80.0}],
            total_dur=100.0,
            max_chunk_dur=30.0,
            margin=0.0,
            gap_merge_limit=0.0,
            settings={"whisper_chunk_overlap_sec": 2.0},
        )

        self.assertEqual(chunks[0], {"start": 10.0, "end": 40.0})
        self.assertEqual(chunks[1], {"start": 38.0, "end": 68.0})
        self.assertEqual(chunks[2], {"start": 66.0, "end": 80.0})

    def test_dedupe_overlapping_segments_uses_word_timestamps(self):
        chunk = [
            {
                "start": 27.0,
                "end": 32.0,
                "text": "중복 앞부분 새 단어",
                "words": [
                    {"word": "중복", "start": 27.0, "end": 28.0},
                    {"word": "앞부분", "start": 28.0, "end": 29.8},
                    {"word": "새", "start": 30.2, "end": 31.0},
                    {"word": "단어", "start": 31.0, "end": 32.0},
                ],
            }
        ]

        deduped = self.processor._dedupe_overlapping_segments(chunk, previous_end=30.0, dedup_window=0.5)

        self.assertEqual(len(deduped), 1)
        self.assertAlmostEqual(deduped[0]["start"], 30.2)
        self.assertEqual(deduped[0]["text"], "새 단어")
        self.assertEqual([w["word"] for w in deduped[0]["words"]], ["새", "단어"])
        self.assertEqual([w["word"] for w in deduped[0]["asr_metadata"]["words"]], ["새", "단어"])

    def test_parse_whisper_payload_attaches_asr_metadata(self):
        payload = {
            "backend": "unit-test",
            "language_probability": 0.93,
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "테스트",
                    "avg_logprob": -0.2,
                    "compression_ratio": 1.1,
                    "no_speech_prob": 0.03,
                    "temperature": 0.0,
                    "words": [
                        {"word": "테스트", "start": 0.1, "end": 0.9, "confidence": 0.88},
                    ],
                }
            ],
        }

        parsed = self.processor._parse_whisper_payload(
            payload,
            {"input_path": "/tmp/chunk.wav", "ov_start_offset": 10.0},
            vad_strict=[{"start": 10.0, "end": 11.0, "review_vad": True}],
        )

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["start"], 10.1)
        self.assertEqual(parsed[0]["end"], 10.9)
        self.assertEqual(parsed[0]["asr_metadata"]["backend"], "unit-test")
        self.assertEqual(parsed[0]["asr_metadata"]["language_probability"], 0.93)
        self.assertEqual(parsed[0]["asr_metadata"]["words"][0]["start"], 10.1)
        self.assertEqual(parsed[0]["asr_metadata"]["vad_alignment"]["vad_aligned"], True)
        self.assertEqual(parsed[0]["quality"]["vad_alignment_score"], 100.0)

    def test_parse_whisper_payload_rebuilds_text_from_filtered_words(self):
        payload = {
            "backend": "unit-test",
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.3,
                    "text": "어 오늘은 여기 고향",
                    "words": [
                        {"word": "어", "start": 0.0, "end": 0.18},
                        {"word": "오늘은", "start": 0.82, "end": 1.1},
                    ],
                }
            ],
        }

        parsed = self.processor._parse_whisper_payload(
            payload,
            {"input_path": "/tmp/chunk.wav", "ov_start_offset": 10.0},
            vad_strict=[{"start": 10.0, "end": 10.3, "vad_word_filter": True}],
        )

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["text"], "어")
        self.assertEqual(parsed[0]["start"], 10.0)
        self.assertEqual(parsed[0]["end"], 10.18)
        self.assertEqual([word["word"] for word in parsed[0]["words"]], ["어"])

    def test_parse_whisper_payload_strips_control_tokens_from_words_and_text(self):
        payload = {
            "backend": "unit-test",
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "어 오늘은 여기 고향",
                    "words": [
                        {"word": "<|4.00|>", "start": 0.0, "end": 0.2},
                        {"word": "2026<|6.00|>", "start": 0.2, "end": 1.0, "confidence": 0.9},
                    ],
                }
            ],
        }

        parsed = self.processor._parse_whisper_payload(
            payload,
            {"input_path": "/tmp/chunk.wav", "ov_start_offset": 4.0},
            vad_strict=[],
        )

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["text"], "2026")
        self.assertEqual(parsed[0]["start"], 4.2)
        self.assertEqual(parsed[0]["end"], 5.0)
        self.assertEqual([word["word"] for word in parsed[0]["words"]], ["2026"])
        self.assertEqual(parsed[0]["asr_metadata"]["words"][0]["word"], "2026")

    def test_post_stt_vad_does_not_filter_words_before_alignment(self):
        payload = {
            "backend": "unit-test",
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "테스트",
                    "words": [{"word": "테스트", "start": 0.1, "end": 0.9}],
                }
            ],
        }

        parsed = self.processor._parse_whisper_payload(
            payload,
            {"input_path": "/tmp/chunk.wav", "ov_start_offset": 10.0},
            vad_strict=[{"start": 30.0, "end": 31.0, "post_stt_align": True, "vad_word_filter": False}],
        )

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["text"], "테스트")

    def test_quality_presets_set_overlap_per_mode(self):
        fast = apply_stt_quality_preset({}, "fast")
        balanced = apply_stt_quality_preset({}, "balanced")
        precise = apply_stt_quality_preset({}, "precise")

        self.assertEqual(fast["ff_chunk"], 180)
        self.assertEqual(fast["whisper_chunk_overlap_sec"], 6.0)
        self.assertLess(fast["whisper_chunk_overlap_sec"], balanced["whisper_chunk_overlap_sec"])
        self.assertEqual(balanced["whisper_chunk_overlap_sec"], 10.0)
        self.assertEqual(precise["ff_chunk"], 120)
        self.assertEqual(precise["whisper_chunk_overlap_sec"], 8.0)
        self.assertTrue(precise["stt_windowed_finalize_enabled"])
        self.assertEqual(precise["stt_window_sec"], 180.0)

    def test_windowed_finalize_allows_long_overlap_for_mode_chunks(self):
        overlap = self.processor._chunk_overlap_sec({
            "ff_chunk": 180,
            "whisper_chunk_overlap_sec": 12.0,
            "stt_windowed_finalize_enabled": True,
        })

        self.assertEqual(overlap, 12.0)

    def test_windowed_finalize_keeps_only_chunk_commit_region(self):
        chunk = [
            {
                "start": 168.0,
                "end": 181.0,
                "text": "앞 겹침 확정 새구간",
                "words": [
                    {"word": "앞", "start": 168.3, "end": 168.8},
                    {"word": "겹침", "start": 170.0, "end": 170.5},
                    {"word": "확정", "start": 174.2, "end": 174.8},
                    {"word": "새구간", "start": 180.2, "end": 180.8},
                ],
                "asr_metadata": {"backend": "unit"},
            }
        ]

        finalized = self.processor._apply_windowed_chunk_finalize(
            chunk,
            {"idx": 1, "ov_start_offset": 168.0, "duration": 180.0},
            {
                "stt_windowed_finalize_enabled": True,
                "stt_window_overlap_sec": 12.0,
                "stt_window_hysteresis_sec": 6.0,
                "stt_window_max_boundary_shift_sec": 0.12,
            },
            total_chunks=3,
            vad_segments=[],
        )

        self.assertEqual(len(finalized), 1)
        self.assertEqual(finalized[0]["text"], "확정 새구간")
        self.assertAlmostEqual(finalized[0]["start"], 174.2)
        self.assertEqual([w["word"] for w in finalized[0]["words"]], ["확정", "새구간"])
        self.assertEqual(finalized[0]["asr_metadata"]["windowed_finalize"]["commit_start"], 174.0)

    def test_windowed_span_ranges_split_long_media_into_three_minute_windows(self):
        items = [
            {"ov_start_offset": float(idx * 30), "duration": 30.0}
            for idx in range(7)
        ]

        ranges = self.processor._windowed_span_ranges(
            items,
            {
                "stt_windowed_finalize_enabled": True,
                "stt_window_sec": 180.0,
                "stt_window_overlap_sec": 12.0,
            },
        )

        self.assertEqual(ranges, [
            {"start": 0.0, "end": 180.0},
            {"start": 168.0, "end": 210.0},
        ])

    def test_windowed_span_finalize_keeps_only_span_commit_region(self):
        chunk = [
            {
                "start": 168.0,
                "end": 181.0,
                "text": "앞 겹침 확정 새구간",
                "words": [
                    {"word": "앞", "start": 168.3, "end": 168.8},
                    {"word": "겹침", "start": 170.0, "end": 170.5},
                    {"word": "확정", "start": 174.2, "end": 174.8},
                    {"word": "새구간", "start": 180.2, "end": 180.8},
                ],
                "asr_metadata": {"backend": "unit"},
            }
        ]

        finalized = self.processor._apply_windowed_span_finalize(
            chunk,
            {"start": 168.0, "end": 348.0},
            {
                "stt_windowed_finalize_enabled": True,
                "stt_window_sec": 180.0,
                "stt_window_overlap_sec": 12.0,
                "stt_window_hysteresis_sec": 6.0,
                "stt_window_max_boundary_shift_sec": 0.12,
            },
            window_index=1,
            total_windows=3,
            previous_end=160.0,
            vad_segments=[],
        )

        self.assertEqual(len(finalized), 1)
        self.assertEqual(finalized[0]["text"], "확정 새구간")
        self.assertAlmostEqual(finalized[0]["start"], 174.2)
        self.assertEqual([w["word"] for w in finalized[0]["words"]], ["확정", "새구간"])
        self.assertEqual(finalized[0]["asr_metadata"]["windowed_span_finalize"]["commit_start"], 174.0)

    def test_transcribe_uses_three_minute_window_restart_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            for idx in range(7):
                path = os.path.join(tmp, f"vad_{idx:03d}_{idx * 30:.3f}.wav")
                with wave.open(path, "wb") as handle:
                    handle.setnchannels(1)
                    handle.setsampwidth(2)
                    handle.setframerate(1)
                    handle.writeframes(struct.pack("<" + "h" * 30, *([0] * 30)))

            self.processor._load_all_settings = lambda: {
                "stt_windowed_finalize_enabled": True,
                "stt_window_sec": 180.0,
                "stt_window_overlap_sec": 12.0,
                "stt_window_hysteresis_sec": 6.0,
                "stt_window_max_boundary_shift_sec": 0.12,
                "stt_early_preview_burst_enabled": False,
                "stt_window_parallel_enabled": False,
                "sub_dedup_window": 0.5,
            }

            calls = []
            preview_calls = []

            def fake_collect(window_chunk_dir, **_kwargs):
                with open(os.path.join(window_chunk_dir, "window_meta.json"), "r", encoding="utf-8") as handle:
                    meta = json.load(handle)
                calls.append(meta)
                if meta["window_index"] == 0:
                    return [
                        {
                            "start": 150.0,
                            "end": 176.0,
                            "text": "첫창 겹침",
                            "asr_metadata": {"backend": "unit"},
                        }
                    ]
                return [
                    {
                        "start": 174.2,
                        "end": 190.0,
                        "text": "둘창 새구간",
                        "asr_metadata": {"backend": "unit"},
                    }
                ]

            self.processor._collect_window_transcribe_segments = fake_collect

            result = list(self.processor.transcribe(
                tmp,
                cleanup_chunk_dir=False,
                preview_callback=lambda segs, label: preview_calls.append((label, list(segs))),
            ))

            self.assertEqual(len(calls), 2)
            self.assertEqual([(item[1], item[2]) for item in result], [(1, 2), (2, 2)])
            self.assertAlmostEqual(result[0][0][0]["end"], 174.0)
            self.assertAlmostEqual(result[1][0][0]["start"], 174.2)
            self.assertEqual(len(preview_calls), 2)

    def test_transcribe_runs_early_preview_before_windowed_spans(self):
        with tempfile.TemporaryDirectory() as tmp:
            for idx in range(7):
                path = os.path.join(tmp, f"vad_{idx:03d}_{idx * 30:.3f}.wav")
                with wave.open(path, "wb") as handle:
                    handle.setnchannels(1)
                    handle.setsampwidth(2)
                    handle.setframerate(1)
                    handle.writeframes(struct.pack("<" + "h" * 30, *([0] * 30)))

            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "primary",
                "stt_windowed_finalize_enabled": True,
                "stt_window_sec": 180.0,
                "stt_window_overlap_sec": 12.0,
            }
            order = []

            def fake_burst(*_args, **_kwargs):
                order.append("preview")

            def fake_windowed(*_args, **_kwargs):
                order.append("windowed")
                yield [{"start": 0.0, "end": 1.0, "text": "final"}], 1, 1

            self.processor._run_early_stt_preview_burst = fake_burst
            self.processor._transcribe_with_windowed_spans = fake_windowed

            result = list(self.processor.transcribe(
                tmp,
                cleanup_chunk_dir=False,
                preview_callback=lambda *_args: None,
            ))

        self.assertEqual(order, ["preview", "windowed"])
        self.assertEqual(result[0][0][0]["text"], "final")

    def test_transcribe_runs_serial_fallback_when_windowed_spans_are_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            for idx in range(7):
                path = os.path.join(tmp, f"vad_{idx:03d}_{idx * 30:.3f}.wav")
                with wave.open(path, "wb") as handle:
                    handle.setnchannels(1)
                    handle.setsampwidth(2)
                    handle.setframerate(1)
                    handle.writeframes(struct.pack("<" + "h" * 30, *([0] * 30)))

            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "primary",
                "stt_windowed_finalize_enabled": True,
                "stt_window_sec": 180.0,
                "stt_window_overlap_sec": 12.0,
            }
            order = []

            def fake_windowed(*_args, **_kwargs):
                order.append("windowed")
                yield [], 1, 1

            def fake_fallback(_chunk_dir, **kwargs):
                order.append(("fallback", kwargs.get("log_label"), kwargs.get("model_override")))
                yield [{"start": 0.0, "end": 1.0, "text": "fallback"}], 1, 1

            self.processor._run_early_stt_preview_burst = lambda *_args, **_kwargs: None
            self.processor._transcribe_with_windowed_spans = fake_windowed
            self.processor._transcribe_zero_window_fallback = fake_fallback

            result = list(self.processor.transcribe(tmp, cleanup_chunk_dir=False, log_label="STT1"))

        self.assertEqual(order, ["windowed", ("fallback", "STT1", None)])
        self.assertEqual(result[0], ([], 1, 1))
        self.assertEqual(result[1][0][0]["text"], "fallback")

    def test_transcribe_runs_serial_fallback_when_windowed_head_gap_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for idx in range(7):
                path = os.path.join(tmp, f"vad_{idx:03d}_{idx * 30:.3f}.wav")
                with wave.open(path, "wb") as handle:
                    handle.setnchannels(1)
                    handle.setsampwidth(2)
                    handle.setframerate(1)
                    handle.writeframes(struct.pack("<" + "h" * 30, *([0] * 30)))

            with open(os.path.join(tmp, "vad_strict.json"), "w", encoding="utf-8") as handle:
                json.dump([{"start": 0.5, "end": 3.0}], handle)

            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "primary",
                "stt_windowed_finalize_enabled": True,
                "stt_window_sec": 180.0,
                "stt_window_overlap_sec": 12.0,
                "stt_window_head_gap_fallback_sec": 45.0,
            }
            order = []

            def fake_windowed(*_args, **_kwargs):
                order.append("windowed")
                yield [{"start": 112.0, "end": 114.0, "text": "late-window"}], 1, 2

            def fake_fallback(_chunk_dir, **kwargs):
                order.append(("fallback", kwargs.get("log_label")))
                yield [{"start": 0.5, "end": 3.0, "text": "fallback-head"}], 1, 1

            self.processor._run_early_stt_preview_burst = lambda *_args, **_kwargs: None
            self.processor._transcribe_with_windowed_spans = fake_windowed
            self.processor._transcribe_zero_window_fallback = fake_fallback

            result = list(self.processor.transcribe(tmp, cleanup_chunk_dir=False, log_label="STT1"))

        self.assertEqual(order, ["windowed", ("fallback", "STT1")])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0][0]["text"], "fallback-head")

    def test_early_stt_preview_burst_emits_preview_only_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            for idx, start in enumerate((0.0, 30.0)):
                path = os.path.join(tmp, f"vad_{idx:03d}_{start:.3f}.wav")
                with wave.open(path, "wb") as handle:
                    handle.setnchannels(1)
                    handle.setsampwidth(2)
                    handle.setframerate(1)
                    handle.writeframes(struct.pack("<" + "h" * 30, *([0] * 30)))

            settings = {
                "selected_whisper_model": "primary",
                "stt_early_preview_burst_sec": 30.0,
                "stt_word_timestamps_mode": "always",
                "stt_word_timestamps_precision_enabled": True,
                "stt_selective_secondary_recheck_enabled": True,
            }
            items = [
                {"idx": 0, "input_path": os.path.join(tmp, "vad_000_0.000.wav"), "ov_start_offset": 0.0, "duration": 30.0},
                {"idx": 1, "input_path": os.path.join(tmp, "vad_001_30.000.wav"), "ov_start_offset": 30.0, "duration": 30.0},
            ]
            preview_calls = []
            captured = {}

            def fake_collect(chunk_dir, model, **kwargs):
                captured["chunk_dir"] = chunk_dir
                captured["model"] = model
                captured["target_end_sec"] = kwargs["target_end_sec"]
                captured["is_single"] = kwargs["is_single"]
                captured["settings_overrides"] = dict(kwargs["settings_overrides"])
                with open(os.path.join(chunk_dir, "window_meta.json"), "r", encoding="utf-8") as handle:
                    captured["window_meta"] = json.load(handle)
                kwargs["preview_callback"]([
                    {"start": 0.2, "end": 1.0, "text": "초반"},
                    {"start": 31.0, "end": 32.0, "text": "뒤쪽"},
                ], "worker")
                return [{"start": 0.2, "end": 1.0, "text": "final-unused"}]

            with patch("core.audio.media_processor_transcribe._stt_memory_pressure_stage", return_value="normal"), \
                 patch.object(self.processor, "_collect_transcribe_result", side_effect=fake_collect):
                returned = self.processor._run_early_stt_preview_burst(
                    tmp,
                    items,
                    settings,
                    target_end_sec=None,
                    is_single=False,
                    model="primary",
                    log_label="STT1",
                    preview_callback=lambda segs, label: preview_calls.append((label, list(segs))),
                    vad_strict=[],
                )

        self.assertIsNone(returned)
        self.assertEqual(captured["model"], "primary")
        self.assertEqual(captured["target_end_sec"], 30.0)
        self.assertTrue(captured["is_single"])
        self.assertEqual(captured["window_meta"]["start"], 0.0)
        self.assertEqual(captured["window_meta"]["end"], 30.0)
        self.assertFalse(os.path.exists(captured["chunk_dir"]))
        overrides = captured["settings_overrides"]
        self.assertFalse(overrides["stt_selective_secondary_recheck_enabled"])
        self.assertFalse(overrides["stt_word_timestamps_precision_enabled"])
        self.assertEqual(overrides["stt_word_timestamps_mode"], "off")
        self.assertEqual(len(preview_calls), 1)
        self.assertEqual(preview_calls[0][0], "STT1-EARLY")
        self.assertEqual([seg["text"] for seg in preview_calls[0][1]], ["초반"])
        self.assertEqual(preview_calls[0][1][0]["stt_ensemble_source"], "STT1_EARLY_PREVIEW")
        self.assertTrue(preview_calls[0][1][0]["asr_metadata"]["early_preview_burst"]["enabled"])

    def test_quality_review_keeps_fast_overlap_short(self):
        overlap = self.processor._chunk_overlap_sec({
            "subtitle_mode": "fast",
            "whisper_chunk_overlap_sec": 0.5,
            "subtitle_quality_auto_check_after_generate": True,
        })

        self.assertEqual(overlap, 0.5)

    def test_quality_review_forces_precise_overlap_outside_fast_mode(self):
        overlap = self.processor._chunk_overlap_sec({
            "subtitle_mode": "auto",
            "whisper_chunk_overlap_sec": 0.5,
            "subtitle_quality_auto_check_after_generate": True,
        })

        self.assertEqual(overlap, 3.0)

    def test_transcribe_progress_log_includes_stt_label(self):
        progress = self.processor._format_transcribe_progress("STT2", 125.0, 600.0, 20)

        self.assertEqual(progress, "  ▶ [STT2] 진행 상황: 02분 05초 / 10분 00초 (20%)")

    def test_transcribe_ensemble_uses_windowed_spans_for_long_high_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            for idx in range(8):
                path = os.path.join(tmp, f"vad_{idx:03d}_{idx * 30:.3f}.wav")
                with wave.open(path, "wb") as handle:
                    handle.setnchannels(1)
                    handle.setsampwidth(2)
                    handle.setframerate(1)
                    handle.writeframes(struct.pack("<" + "h" * 30, *([0] * 30)))

            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "primary",
                "selected_whisper_model_secondary": "secondary",
                "stt_ensemble_enabled": True,
                "stt_windowed_finalize_enabled": True,
                "stt_window_sec": 120.0,
                "stt_window_overlap_sec": 8.0,
                "stt_window_hysteresis_sec": 4.0,
            }

            calls = {}

            def fake_windowed(window_chunk_dir, items, settings, **kwargs):
                calls["chunk_dir"] = window_chunk_dir
                calls["items"] = list(items)
                calls["settings"] = dict(settings)
                calls["log_label"] = kwargs.get("log_label")
                yield [{"start": 0.0, "end": 1.0, "text": "rolled"}], 1, 2

            self.processor._transcribe_with_windowed_spans = fake_windowed

            result = list(self.processor.transcribe_ensemble(tmp, cleanup_chunk_dir=False))

            self.assertEqual(calls["chunk_dir"], tmp)
            self.assertEqual(calls["log_label"], "STT-ENSEMBLE")
            self.assertEqual(len(calls["items"]), 8)
            self.assertTrue(calls["settings"]["stt_windowed_finalize_enabled"])
            self.assertEqual(result[0][0][0]["text"], "rolled")
            self.assertEqual(result[0][1:], (1, 2))

    def test_transcribe_ensemble_runs_serial_fallback_when_windowed_spans_are_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            for idx in range(8):
                path = os.path.join(tmp, f"vad_{idx:03d}_{idx * 30:.3f}.wav")
                with wave.open(path, "wb") as handle:
                    handle.setnchannels(1)
                    handle.setsampwidth(2)
                    handle.setframerate(1)
                    handle.writeframes(struct.pack("<" + "h" * 30, *([0] * 30)))

            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "primary",
                "selected_whisper_model_secondary": "secondary",
                "stt_ensemble_enabled": True,
                "stt_windowed_finalize_enabled": True,
                "stt_window_sec": 120.0,
                "stt_window_overlap_sec": 8.0,
            }
            order = []

            def fake_windowed(*_args, **_kwargs):
                order.append("windowed")
                yield [], 1, 1

            def fake_fallback(_chunk_dir, **_kwargs):
                order.append("fallback")
                yield [{"start": 0.0, "end": 1.0, "text": "ensemble fallback"}], 1, 1

            self.processor._run_early_stt_preview_burst = lambda *_args, **_kwargs: None
            self.processor._transcribe_with_windowed_spans = fake_windowed
            self.processor._transcribe_ensemble_zero_window_fallback = fake_fallback

            result = list(self.processor.transcribe_ensemble(tmp, cleanup_chunk_dir=False))

        self.assertEqual(order, ["windowed", "fallback"])
        self.assertEqual(result[0], ([], 1, 1))
        self.assertEqual(result[1][0][0]["text"], "ensemble fallback")

    def test_transcribe_ensemble_runs_serial_fallback_when_windowed_head_gap_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for idx in range(8):
                path = os.path.join(tmp, f"vad_{idx:03d}_{idx * 30:.3f}.wav")
                with wave.open(path, "wb") as handle:
                    handle.setnchannels(1)
                    handle.setsampwidth(2)
                    handle.setframerate(1)
                    handle.writeframes(struct.pack("<" + "h" * 30, *([0] * 30)))

            with open(os.path.join(tmp, "vad_strict.json"), "w", encoding="utf-8") as handle:
                json.dump([{"start": 1.0, "end": 4.0}], handle)

            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "primary",
                "selected_whisper_model_secondary": "secondary",
                "stt_ensemble_enabled": True,
                "stt_windowed_finalize_enabled": True,
                "stt_window_sec": 120.0,
                "stt_window_overlap_sec": 8.0,
                "stt_window_head_gap_fallback_sec": 45.0,
            }
            order = []

            def fake_windowed(*_args, **_kwargs):
                order.append("windowed")
                yield [{"start": 91.0, "end": 93.0, "text": "late-ensemble"}], 1, 2

            def fake_fallback(_chunk_dir, **_kwargs):
                order.append("fallback")
                yield [{"start": 1.0, "end": 4.0, "text": "ensemble-head"}], 1, 1

            self.processor._run_early_stt_preview_burst = lambda *_args, **_kwargs: None
            self.processor._transcribe_with_windowed_spans = fake_windowed
            self.processor._transcribe_ensemble_zero_window_fallback = fake_fallback

            result = list(self.processor.transcribe_ensemble(tmp, cleanup_chunk_dir=False))

        self.assertEqual(order, ["windowed", "fallback"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0][0]["text"], "ensemble-head")

    def test_ensemble_preview_callback_receives_stt2_segments(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = os.path.join(tmp, "vad_000_0.000.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00\x00" * 16000)
            calls = []

            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "primary",
                "selected_whisper_model_secondary": "secondary",
                "stt_workers_auto_enabled": False,
                "vad_post_stt_align_enabled": False,
            }

            def fake_collect(_chunk_dir, _model, *, label, preview_callback=None, **_kwargs):
                seg = {
                    "start": 0.0 if label == "STT1" else 1.0,
                    "end": 0.8 if label == "STT1" else 1.8,
                    "text": label,
                }
                if callable(preview_callback):
                    preview_callback([dict(seg)], label)
                return [seg]

            self.processor._collect_transcribe_result = fake_collect

            result = list(self.processor.transcribe_ensemble(
                tmp,
                preview_callback=lambda segs, label: calls.append((label, list(segs))),
            ))

            self.assertEqual({label for label, _ in calls}, {"STT1", "STT2"})
            stt2_call = next(segs for label, segs in calls if label == "STT2")
            self.assertEqual(stt2_call[0]["text"], "STT2")

    def test_collect_transcribe_result_disables_nested_window_rolling(self):
        class _Worker(VideoProcessor):
            last_kwargs = None

            def transcribe(self, *args, **kwargs):
                type(self).last_kwargs = dict(kwargs)
                yield [], 1, 1

            def stop_transcribe(self):
                return None

        worker = _Worker()
        worker._load_all_settings = lambda: {}

        result = worker._collect_transcribe_result(
            "/tmp/does-not-matter",
            "unit-model",
            label="STT2",
        )

        self.assertEqual(result, [])
        self.assertIsNotNone(_Worker.last_kwargs)
        self.assertFalse(_Worker.last_kwargs["_allow_window_rolling"])

    def test_ensemble_runs_stt1_and_stt2_on_parallel_threads(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = os.path.join(tmp, "vad_000_0.000.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00\x00" * 16000)
            barrier = threading.Barrier(2)
            thread_names = {}
            preview_calls = []

            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "primary",
                "selected_whisper_model_secondary": "secondary",
                "stt_workers_auto_enabled": False,
                "vad_post_stt_align_enabled": False,
            }

            def fake_collect(_chunk_dir, _model, *, label, preview_callback=None, **_kwargs):
                thread_names[label] = threading.current_thread().name
                barrier.wait(timeout=2.0)
                seg = {"start": 0.0, "end": 0.8, "text": label}
                if callable(preview_callback):
                    preview_callback([seg], label)
                    seg["text"] = "mutated-after-preview"
                return [{"start": 0.0, "end": 0.8, "text": label}]

            self.processor._collect_transcribe_result = fake_collect

            result = list(self.processor.transcribe_ensemble(
                tmp,
                preview_callback=lambda segs, label: preview_calls.append((label, list(segs))),
            ))

            self.assertEqual(set(thread_names), {"STT1", "STT2"})
            self.assertNotEqual(thread_names["STT1"], thread_names["STT2"])
            self.assertEqual({label for label, _ in preview_calls}, {"STT1", "STT2"})
            self.assertNotIn("mutated-after-preview", [segs[0]["text"] for _, segs in preview_calls])
            self.assertEqual(result[0][1:], (1, 1))

    def test_selective_ensemble_runs_stt2_only_for_low_score_ranges(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = os.path.join(tmp, "vad_000_0.000.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00\x00" * 16000)

            calls = []
            preview_calls = []
            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "primary",
                "selected_whisper_model_secondary": "secondary",
                "stt_ensemble_selective_enabled": True,
                "stt_ensemble_parallel_enabled": False,
                "stt_low_score_recheck_enabled": True,
                "stt_low_score_recheck_threshold": 80,
                "stt_low_score_recheck_max_segments": 4,
                "stt_word_timestamps_precision_enabled": False,
                "vad_post_stt_align_enabled": False,
            }

            def fake_collect(_chunk_dir, _model, *, label, preview_callback=None, **_kwargs):
                calls.append((label, dict(_kwargs.get("settings_overrides") or {})))
                if label == "STT1":
                    if callable(preview_callback):
                        preview_callback([{"start": 0.0, "end": 1.0, "text": "STT1 미리보기"}], label)
                    return [{
                        "start": 0.0,
                        "end": 1.0,
                        "text": "낮은 후보",
                        "stt_score": 35,
                        "score": 35,
                        "chunk_path": wav_path,
                        "asr_metadata": {"chunk_path": wav_path},
                    }]
                if callable(preview_callback):
                    preview_callback([{"start": 0.0, "end": 1.0, "text": "STT2 미리보기"}], label)
                return [{
                    "start": 0.0,
                    "end": 1.0,
                    "text": "보강 후보",
                    "stt_score": 96,
                    "score": 96,
                    "words": [{"word": "보강", "start": 0.1, "end": 0.4}],
                    "chunk_path": wav_path,
                    "asr_metadata": {"chunk_path": wav_path},
                }]

            self.processor._collect_transcribe_result = fake_collect
            self.processor._prepare_recheck_clip = lambda item, _out_dir, _idx, _settings: {
                "range": item,
                "path": wav_path,
                "start": item.start,
                "end": item.end,
            }

            with patch("core.audio.stt_candidate_scorer.annotate_stt_candidates", side_effect=lambda segments, **_kwargs: segments):
                result = list(self.processor.transcribe_ensemble(
                    tmp,
                    preview_callback=lambda segs, label: preview_calls.append((label, list(segs))),
                    cleanup_chunk_dir=False,
                ))

            self.assertEqual([label for label, _overrides in calls], ["STT1", "Fast-STT2"])
            self.assertIn("STT2", [label for label, _segs in preview_calls])
            stt2_preview = next(segs for label, segs in preview_calls if label == "STT2")
            self.assertEqual(stt2_preview[0]["text"], "STT2 미리보기")
            self.assertFalse(calls[0][1]["stt_word_timestamps_precision_enabled"])
            self.assertEqual(calls[1][1]["stt_word_timestamps_mode"], "off")
            self.assertFalse(calls[1][1]["stt_word_timestamps_default_enabled"])
            self.assertFalse(calls[1][1]["stt_word_timestamps_precision_enabled"])
            self.assertFalse(calls[1][1]["stt_persistent_runtime_reuse_enabled"])
            self.assertEqual(result[0][0][0]["text"], "보강 후보")
            self.assertEqual(result[0][0][0]["stt_ensemble_source"], "STT2_SELECTIVE_RECHECK")

    def test_window_parallel_uses_aggressive_cap_for_three_minute_windows(self):
        with patch("core.audio.media_processor_transcribe._stt_memory_pressure_stage", return_value="normal"), \
             patch("core.audio.media_processor_transcribe.runtime_parallel_worker_plan", return_value=(4, {})) as planner:
            workers, _meta = self.processor._stt_quarter_parallel_window_workers({}, 4)

        self.assertEqual(workers, 4)
        self.assertEqual(planner.call_args.kwargs["maximum"], 4)
        self.assertEqual(planner.call_args.kwargs["requested"], 4)

    def test_window_parallel_caps_shorter_windows_to_guard_quality(self):
        with patch("core.audio.media_processor_transcribe._stt_memory_pressure_stage", return_value="normal"), \
             patch("core.audio.media_processor_transcribe.runtime_parallel_worker_plan", return_value=(2, {})) as planner:
            workers, _meta = self.processor._stt_quarter_parallel_window_workers(
                {"stt_window_sec": 90.0},
                4,
            )

        self.assertEqual(workers, 2)
        self.assertEqual(planner.call_args.kwargs["requested"], 2)

    def test_window_parallel_can_be_disabled_explicitly(self):
        with patch("core.audio.media_processor_transcribe.runtime_parallel_worker_plan") as planner:
            workers, meta = self.processor._stt_quarter_parallel_window_workers(
                {"stt_window_parallel_enabled": False},
                4,
            )

        self.assertEqual(workers, 1)
        self.assertEqual(meta, {})
        planner.assert_not_called()

    def test_window_isolated_worker_can_run_stt_ensemble_inside_each_window(self):
        calls: list[dict] = []

        def fake_ensemble(worker, window_chunk_dir, **kwargs):
            calls.append({
                "window_chunk_dir": window_chunk_dir,
                "settings": dict(getattr(worker, "_fast_mode_overrides", {}) or {}),
                "kwargs": dict(kwargs),
            })
            yield ([{"start": 0.0, "end": 1.0, "text": "ensemble-window"}], 1, 1)

        with patch.object(type(self.processor), "transcribe_ensemble", fake_ensemble), \
             patch.object(type(self.processor), "transcribe", side_effect=AssertionError("single STT path should not run")), \
             patch.object(type(self.processor), "release_runtime_models", return_value=None):
            rows = self.processor._collect_window_transcribe_segments_isolated(
                "/tmp/window_ensemble",
                settings={"stt_window_ensemble_enabled": True},
                target_end_sec=180.0,
                is_single=False,
                model_override=None,
                log_label="TEST",
                use_ensemble=True,
            )

        self.assertEqual(rows[0]["text"], "ensemble-window")
        self.assertEqual(calls[0]["window_chunk_dir"], "/tmp/window_ensemble")
        self.assertTrue(calls[0]["settings"]["stt_window_ensemble_enabled"])
        self.assertFalse(calls[0]["kwargs"]["_allow_window_rolling"])

    def test_windowed_quarter_parallel_preserves_final_commit_order(self):
        window_ranges = [
            {"start": 0.0, "end": 60.0},
            {"start": 55.0, "end": 115.0},
            {"start": 110.0, "end": 170.0},
            {"start": 165.0, "end": 225.0},
        ]
        items = [{"input_path": f"chunk_{idx}.wav", "ov_start_offset": idx * 55.0, "duration": 55.0} for idx in range(4)]
        settings = {
            "stt_windowed_finalize_enabled": True,
            "stt_window_sec": 60.0,
            "stt_quarter_parallel_experiment_enabled": True,
            "stt_quarter_parallel_count": 4,
            "stt_quarter_parallel_max_workers": 2,
        }
        active = 0
        max_active = 0
        lock = threading.Lock()
        finalize_order: list[int] = []

        self.processor._windowed_span_ranges = lambda _items, _settings: list(window_ranges)
        self.processor._window_items_for_range = lambda _items, start, _end: [dict(_items[int(start // 55.0)])]
        self.processor._clip_vad_segments_to_window = lambda *_args, **_kwargs: []
        self.processor._build_window_chunk_dir = (
            lambda _base, _items, *, window_index, **_kwargs: f"/tmp/window_{window_index}"
        )

        def fake_collect(window_chunk_dir, **_kwargs):
            nonlocal active, max_active
            window_index = int(str(window_chunk_dir).rsplit("_", 1)[-1])
            with lock:
                active += 1
                max_active = max(max_active, active)
            try:
                time.sleep(0.02)
                return [{"start": window_index * 55.0, "end": window_index * 55.0 + 10.0, "text": f"w{window_index}"}]
            finally:
                with lock:
                    active -= 1

        def fake_finalize(window_segments, _window_range, _settings, *, window_index, **_kwargs):
            finalize_order.append(window_index)
            return list(window_segments)

        self.processor._collect_window_transcribe_segments_isolated = fake_collect
        self.processor._apply_windowed_span_finalize = fake_finalize

        with patch("core.audio.media_processor_transcribe._stt_memory_pressure_stage", return_value="normal"), \
             patch("core.audio.media_processor_transcribe.runtime_parallel_worker_plan", return_value=(2, {})):
            result = list(self.processor._transcribe_with_windowed_spans(
                "/tmp/chunks",
                items,
                settings,
                vad_strict=[],
                target_end_sec=None,
                is_single=False,
                model_override=None,
                log_label="TEST",
            ))

        self.assertGreaterEqual(max_active, 2)
        self.assertEqual(finalize_order, [0, 1, 2, 3])
        self.assertEqual([idx for _segments, idx, _total in result], [1, 2, 3, 4])
        self.assertEqual([segments[0]["text"] for segments, _idx, _total in result], ["w0", "w1", "w2", "w3"])

    def test_windowed_quarter_parallel_passes_ensemble_flag_to_window_workers(self):
        window_ranges = [
            {"start": 0.0, "end": 60.0},
            {"start": 55.0, "end": 115.0},
        ]
        items = [{"input_path": f"chunk_{idx}.wav", "ov_start_offset": idx * 55.0, "duration": 55.0} for idx in range(2)]
        settings = {
            "stt_windowed_finalize_enabled": True,
            "stt_window_sec": 60.0,
            "stt_window_ensemble_enabled": True,
            "stt_quarter_parallel_count": 4,
            "stt_quarter_parallel_max_workers": 2,
        }
        use_ensemble_flags: list[bool] = []

        self.processor._windowed_span_ranges = lambda _items, _settings: list(window_ranges)
        self.processor._window_items_for_range = lambda _items, start, _end: [dict(_items[int(start // 55.0)])]
        self.processor._clip_vad_segments_to_window = lambda *_args, **_kwargs: []
        self.processor._build_window_chunk_dir = (
            lambda _base, _items, *, window_index, **_kwargs: f"/tmp/window_{window_index}"
        )
        self.processor._collect_window_transcribe_segments_isolated = (
            lambda _window_chunk_dir, **kwargs: (
                use_ensemble_flags.append(bool(kwargs.get("use_ensemble"))) or
                [{"start": 0.0, "end": 1.0, "text": "ok"}]
            )
        )
        self.processor._apply_windowed_span_finalize = (
            lambda window_segments, _window_range, _settings, **_kwargs: list(window_segments)
        )

        with patch("core.audio.media_processor_transcribe._stt_memory_pressure_stage", return_value="normal"), \
             patch("core.audio.media_processor_transcribe.runtime_parallel_worker_plan", return_value=(2, {})):
            list(self.processor._transcribe_with_windowed_spans(
                "/tmp/chunks",
                items,
                settings,
                vad_strict=[],
                target_end_sec=None,
                is_single=False,
                model_override=None,
                log_label="TEST",
                use_ensemble_windows=True,
            ))

        self.assertEqual(use_ensemble_flags, [True, True])

    def test_windowed_quarter_parallel_streams_first_ready_window_without_waiting_for_tail(self):
        window_ranges = [
            {"start": 0.0, "end": 60.0},
            {"start": 55.0, "end": 115.0},
        ]
        items = [{"input_path": f"chunk_{idx}.wav", "ov_start_offset": idx * 55.0, "duration": 55.0} for idx in range(2)]
        settings = {
            "stt_windowed_finalize_enabled": True,
            "stt_window_sec": 60.0,
            "stt_quarter_parallel_experiment_enabled": True,
            "stt_quarter_parallel_count": 4,
            "stt_quarter_parallel_max_workers": 2,
        }
        first_ready = threading.Event()
        release_tail = threading.Event()
        first_result: list[tuple[list[dict], int, int]] = []

        self.processor._windowed_span_ranges = lambda _items, _settings: list(window_ranges)
        self.processor._window_items_for_range = lambda _items, start, _end: [dict(_items[int(start // 55.0)])]
        self.processor._clip_vad_segments_to_window = lambda *_args, **_kwargs: []
        self.processor._build_window_chunk_dir = (
            lambda _base, _items, *, window_index, **_kwargs: f"/tmp/window_{window_index}"
        )

        def fake_collect(window_chunk_dir, **_kwargs):
            window_index = int(str(window_chunk_dir).rsplit("_", 1)[-1])
            if window_index == 0:
                first_ready.set()
                return [{"start": 0.0, "end": 10.0, "text": "w0"}]
            first_ready.wait(timeout=1.0)
            release_tail.wait(timeout=1.0)
            return [{"start": 55.0, "end": 65.0, "text": "w1"}]

        self.processor._collect_window_transcribe_segments_isolated = fake_collect
        self.processor._apply_windowed_span_finalize = (
            lambda window_segments, _window_range, _settings, **_kwargs: list(window_segments)
        )

        with patch("core.audio.media_processor_transcribe._stt_memory_pressure_stage", return_value="normal"), \
             patch("core.audio.media_processor_transcribe.runtime_parallel_worker_plan", return_value=(2, {})):
            generator = self.processor._transcribe_with_windowed_spans(
                "/tmp/chunks",
                items,
                settings,
                vad_strict=[],
                target_end_sec=None,
                is_single=False,
                model_override=None,
                log_label="TEST",
            )

            consumer = threading.Thread(target=lambda: first_result.append(next(generator)))
            consumer.start()
            first_ready.wait(timeout=1.0)
            consumer.join(timeout=0.2)
            self.assertFalse(consumer.is_alive())
            self.assertEqual(first_result[0][1], 1)
            self.assertEqual(first_result[0][0][0]["text"], "w0")

            release_tail.set()
            tail = list(generator)
            consumer.join(timeout=1.0)
        self.assertEqual([idx for _segments, idx, _total in tail], [2])

    def test_chunk_sort_key_uses_timeline_offset_not_filename_order(self):
        names = [
            "vad_1000_1440.000.wav",
            "vad_900_10.000.wav",
            "vad_901_20.000.wav",
        ]

        ordered = sorted(names, key=self.processor._chunk_sort_key)

        self.assertEqual(ordered, [
            "vad_900_10.000.wav",
            "vad_901_20.000.wav",
            "vad_1000_1440.000.wav",
        ])

    def test_selective_ensemble_rechecks_missing_vad_voice_ranges(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = os.path.join(tmp, "vad_000_0.000.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00\x00" * 16000 * 4)
            with open(os.path.join(tmp, "vad_strict.json"), "w", encoding="utf-8") as handle:
                json.dump([{"start": 0.0, "end": 0.5}, {"start": 2.0, "end": 3.0}], handle)

            calls = []
            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "primary",
                "selected_whisper_model_secondary": "secondary",
                "stt_ensemble_selective_enabled": True,
                "stt_ensemble_parallel_enabled": False,
                "stt_low_score_recheck_enabled": True,
                "stt_low_score_recheck_threshold": 60,
                "stt_low_score_recheck_max_segments": 4,
                "stt_word_timestamps_precision_enabled": False,
                "stt_missing_voice_min_duration_sec": 0.55,
                "vad_post_stt_align_enabled": False,
            }

            def fake_collect(_chunk_dir, _model, *, label, **_kwargs):
                calls.append(label)
                if label == "STT1":
                    return [{
                        "start": 0.0,
                        "end": 0.5,
                        "text": "기존 후보",
                        "stt_score": 92,
                        "score": 92,
                        "chunk_path": wav_path,
                        "asr_metadata": {"chunk_path": wav_path},
                    }]
                return [{
                    "start": 2.0,
                    "end": 2.6,
                    "text": "누락 보강",
                    "stt_score": 94,
                    "score": 94,
                    "chunk_path": wav_path,
                    "asr_metadata": {"chunk_path": wav_path},
                }]

            self.processor._collect_transcribe_result = fake_collect
            self.processor._prepare_recheck_clip = lambda item, _out_dir, _idx, _settings: {
                "range": item,
                "path": wav_path,
                "start": item.start,
                "end": item.end,
            }

            with patch("core.audio.stt_candidate_scorer.annotate_stt_candidates", side_effect=lambda segments, **_kwargs: segments):
                result = list(self.processor.transcribe_ensemble(tmp, cleanup_chunk_dir=False))

            self.assertEqual(calls, ["STT1", "Fast-STT2"])
            self.assertEqual([seg["text"] for seg in result[0][0]], ["기존 후보", "누락 보강"])

    def test_selective_ensemble_deduplicates_overlapping_route_hint_ranges_before_recheck(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = os.path.join(tmp, "vad_000_0.000.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00\x00" * 16000 * 4)
            with open(os.path.join(tmp, "vad_strict.json"), "w", encoding="utf-8") as handle:
                json.dump([], handle)

            prepare_calls = []
            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "primary",
                "selected_whisper_model_secondary": "secondary",
                "stt_ensemble_selective_enabled": True,
                "stt_ensemble_parallel_enabled": False,
                "stt_low_score_recheck_enabled": True,
                "stt_low_score_recheck_threshold": 60,
                "stt_low_score_recheck_max_segments": 4,
                "stt_word_timestamps_precision_enabled": False,
                "vad_post_stt_align_enabled": False,
            }

            def fake_collect(_chunk_dir, _model, *, label, **_kwargs):
                if label == "STT1":
                    return [{
                        "start": 0.0,
                        "end": 1.0,
                        "text": "중복 후보",
                        "stt_score": 28,
                        "score": 28,
                        "stt_route_secondary_recheck_hint": True,
                        "chunk_path": wav_path,
                        "asr_metadata": {"chunk_path": wav_path},
                    }]
                return [{
                    "start": 0.0,
                    "end": 0.9,
                    "text": "보강 결과",
                    "stt_score": 94,
                    "score": 94,
                    "chunk_path": wav_path,
                    "asr_metadata": {"chunk_path": wav_path},
                }]

            self.processor._collect_transcribe_result = fake_collect

            def fake_prepare(item, _out_dir, _idx, _settings):
                prepare_calls.append((round(item.start, 2), round(item.end, 2)))
                return {
                    "range": item,
                    "path": wav_path,
                    "start": item.start,
                    "end": item.end,
                }

            self.processor._prepare_recheck_clip = fake_prepare

            with patch("core.audio.stt_candidate_scorer.annotate_stt_candidates", side_effect=lambda segments, **_kwargs: segments):
                result = list(self.processor.transcribe_ensemble(tmp, cleanup_chunk_dir=False))

            self.assertEqual(prepare_calls, [(0.0, 1.0)])
            self.assertEqual([seg["text"] for seg in result[0][0]], ["보강 결과"])

    def test_ensemble_uses_isolated_chunk_dirs_for_each_track(self):
        with tempfile.TemporaryDirectory() as tmp:
            chunk_dir = os.path.join(tmp, "chunks")
            os.makedirs(chunk_dir, exist_ok=True)
            wav_path = os.path.join(chunk_dir, "vad_000_0.000.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00\x00" * 16000)

            captured_dirs = {}
            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "primary",
                "selected_whisper_model_secondary": "secondary",
                "stt_workers_auto_enabled": False,
                "vad_post_stt_align_enabled": False,
            }

            def fake_collect(local_chunk_dir, _model, *, label, **_kwargs):
                captured_dirs[label] = local_chunk_dir
                local_wav = os.path.join(local_chunk_dir, "vad_000_0.000.wav")
                self.assertTrue(os.path.exists(local_wav))
                if label == "STT1":
                    os.remove(local_wav)
                return [{"start": 0.0, "end": 0.8, "text": label}]

            self.processor._collect_transcribe_result = fake_collect

            result = list(self.processor.transcribe_ensemble(chunk_dir))

            self.assertEqual(result[0][1:], (1, 1))
            self.assertEqual(set(captured_dirs), {"STT1", "STT2"})
            self.assertNotEqual(captured_dirs["STT1"], chunk_dir)
            self.assertNotEqual(captured_dirs["STT2"], chunk_dir)
            self.assertNotEqual(captured_dirs["STT1"], captured_dirs["STT2"])
            self.assertFalse(os.path.exists(captured_dirs["STT1"]))
            self.assertFalse(os.path.exists(captured_dirs["STT2"]))

    def test_ensemble_chunk_clone_prefers_linked_files_over_byte_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            chunk_dir = os.path.join(tmp, "chunks")
            os.makedirs(os.path.join(chunk_dir, ".ensemble_old"), exist_ok=True)
            wav_path = os.path.join(chunk_dir, "vad_000_0.000.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00\x00" * 16000)
            with open(os.path.join(chunk_dir, "vad_strict.json"), "w", encoding="utf-8") as handle:
                json.dump([{"start": 0.0, "end": 1.0}], handle)
            with open(os.path.join(chunk_dir, ".ensemble_old", "ignored.wav"), "wb") as handle:
                handle.write(b"ignored")

            link_calls = []

            def fake_link(src, dst):
                link_calls.append((src, dst))
                with open(src, "rb") as in_handle, open(dst, "wb") as out_handle:
                    out_handle.write(in_handle.read())

            with patch("core.audio.media_processor_transcribe.os.link", side_effect=fake_link), patch(
                "core.audio.media_processor_transcribe.shutil.copy2",
                side_effect=AssertionError("hardlink fast path should avoid byte-copy fallback"),
            ):
                clone = self.processor._clone_ensemble_chunk_dir(chunk_dir, "STT1")

            try:
                self.assertGreaterEqual(len(link_calls), 2)
                self.assertTrue(os.path.exists(os.path.join(clone, "vad_000_0.000.wav")))
                self.assertTrue(os.path.exists(os.path.join(clone, "vad_strict.json")))
                self.assertFalse(os.path.exists(os.path.join(clone, ".ensemble_old", "ignored.wav")))
                os.remove(os.path.join(clone, "vad_000_0.000.wav"))
                self.assertTrue(os.path.exists(wav_path))
            finally:
                if os.path.exists(clone):
                    import shutil

                    shutil.rmtree(clone, ignore_errors=True)

    def test_ensemble_chunk_clone_falls_back_to_copy_when_link_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            chunk_dir = os.path.join(tmp, "chunks")
            os.makedirs(chunk_dir, exist_ok=True)
            wav_path = os.path.join(chunk_dir, "vad_000_0.000.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x01\x00" * 16000)

            copy_calls = []

            def fake_copy(src, dst):
                copy_calls.append((src, dst))
                with open(src, "rb") as in_handle, open(dst, "wb") as out_handle:
                    out_handle.write(in_handle.read())

            with patch("core.audio.media_processor_transcribe.os.link", side_effect=OSError("cross-device")), patch(
                "core.audio.media_processor_transcribe.shutil.copy2",
                side_effect=fake_copy,
            ):
                clone = self.processor._clone_ensemble_chunk_dir(chunk_dir, "STT2")

            try:
                self.assertEqual(len(copy_calls), 1)
                cloned_wav = os.path.join(clone, "vad_000_0.000.wav")
                self.assertTrue(os.path.exists(cloned_wav))
                self.assertEqual(os.path.getsize(cloned_wav), os.path.getsize(wav_path))
            finally:
                if os.path.exists(clone):
                    import shutil

                    shutil.rmtree(clone, ignore_errors=True)

    def test_ensemble_respects_cleanup_chunk_dir_false_for_benchmarks(self):
        with tempfile.TemporaryDirectory() as tmp:
            chunk_dir = os.path.join(tmp, "chunks")
            os.makedirs(chunk_dir, exist_ok=True)
            wav_path = os.path.join(chunk_dir, "vad_000_0.000.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00\x00" * 16000)

            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "primary",
                "selected_whisper_model_secondary": "secondary",
                "stt_workers_auto_enabled": False,
                "vad_post_stt_align_enabled": False,
            }

            def fake_collect(_local_chunk_dir, _model, *, label, **_kwargs):
                return [{"start": 0.0, "end": 0.8, "text": label}]

            self.processor._collect_transcribe_result = fake_collect

            list(self.processor.transcribe_ensemble(chunk_dir, cleanup_chunk_dir=False))

            self.assertTrue(os.path.exists(chunk_dir))
            self.assertTrue(os.path.exists(wav_path))

    def test_normalize_scored_tracks_filters_stt1_and_stt2_with_same_rule(self):
        tracks = {
            "STT1": [
                {"start": 0.0, "end": 1.0, "text": "정상 문장", "stt_score": 78, "stt_score_flags": ["ok"]},
                {"start": 1.0, "end": 2.0, "text": "반복 반복 반복 반복", "stt_score": 45, "stt_score_flags": ["repetition_hallucination_risk"]},
            ],
            "STT2": [
                {"start": 0.0, "end": 1.0, "text": "다른 정상 문장", "stt_score": 74, "stt_score_flags": ["ok"]},
                {"start": 1.0, "end": 2.0, "text": "시청해주셔서 감사합니다", "stt_score": 66, "stt_score_flags": ["known_hallucination_phrase"]},
            ],
        }

        normalized = self.processor._normalize_scored_stt_tracks(
            tracks,
            {"stt_candidate_keep_score": 24},
        )

        self.assertEqual([seg["text"] for seg in normalized["STT1"]], ["정상 문장"])
        self.assertEqual([seg["text"] for seg in normalized["STT2"]], ["다른 정상 문장"])

    def test_recheck_replaces_both_stt_tracks_for_low_score_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = {
                "STT1": [{"start": 0.0, "end": 1.0, "text": "원본1", "stt_score": 31}],
                "STT2": [{"start": 0.0, "end": 1.0, "text": "원본2", "stt_score": 29}],
            }
            settings = {
                "stt_low_score_recheck_enabled": True,
                "stt_low_score_recheck_threshold": 50,
            }

            self.processor._prepare_recheck_clip = lambda item, _out_dir, _idx, _settings: {
                "range": item,
                "start": item.start,
                "end": item.end,
            }
            self.processor._collect_transcribe_result = lambda *_args, **_kwargs: [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "재검사",
                    "avg_logprob": -0.12,
                    "no_speech_prob": 0.01,
                    "compression_ratio": 1.0,
                    "words": [{"word": "재검사", "start": 0.05, "end": 0.95, "confidence": 0.93}],
                }
            ]

            updated = self.processor._recheck_low_score_stt_ranges(
                tmp,
                results,
                settings,
                [],
                "primary-model",
            )

            self.assertEqual([seg["text"] for seg in updated["STT1"]], ["재검사"])
            self.assertEqual([seg["text"] for seg in updated["STT2"]], ["재검사"])
            self.assertTrue(updated["STT1"][0]["stt_recheck_applied"])
            self.assertTrue(updated["STT2"][0]["stt_recheck_applied"])

    def test_vad_empty_does_not_force_split_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_output_dir = config.OUTPUT_DIR
            config.OUTPUT_DIR = tmp
            try:
                video_path = os.path.join(tmp, "silent.mp4")
                open(video_path, "wb").close()

                def write_silent_wav(path: str, seconds: float = 4.0):
                    frames = int(16000 * seconds)
                    with wave.open(path, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(16000)
                        wf.writeframes(b"\x00\x00" * frames)

                def fake_run(cmd, *, label, timeout=None):
                    if label == "ffmpeg 오디오 추출":
                        write_silent_wav(cmd[-1])
                    elif "음량 평탄화" in label:
                        write_silent_wav(cmd[-1])
                    return True

                self.processor._load_all_settings = lambda: {
                    "selected_audio_ai": "none",
                    "selected_vad": "silero",
                    "vad_pre_split_enabled": True,
                    "use_basic_filter": False,
                }
                self.processor._run_media_command = fake_run
                self.processor._split_with_vad = lambda *args, **kwargs: (False, [])
                self.processor._write_grouped_chunks_parallel = (
                    lambda *args, **kwargs: self.fail("VAD empty must not force-split by default")
                )

                chunk_dir, vad_segments = self.processor.extract_audio(video_path)

                self.assertEqual(vad_segments, [])
                self.assertTrue(os.path.isdir(chunk_dir))
                self.assertEqual([f for f in os.listdir(chunk_dir) if f.endswith(".wav")], [])
            finally:
                config.OUTPUT_DIR = old_output_dir

    def test_vad_empty_with_audio_activity_uses_force_split_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_output_dir = config.OUTPUT_DIR
            config.OUTPUT_DIR = tmp
            try:
                video_path = os.path.join(tmp, "active.mp4")
                open(video_path, "wb").close()

                def write_active_wav(path: str, seconds: float = 4.0):
                    frames = int(16000 * seconds)
                    samples = [
                        int(9000 * (1 if i % 2 == 0 else -1))
                        for i in range(frames)
                    ]
                    with wave.open(path, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(16000)
                        wf.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))

                def fake_run(cmd, *, label, timeout=None):
                    if label == "ffmpeg 오디오 추출":
                        write_active_wav(cmd[-1])
                    elif "음량 평탄화" in label:
                        write_active_wav(cmd[-1])
                    return True

                written = []
                self.processor._load_all_settings = lambda: {
                    "selected_audio_ai": "none",
                    "selected_vad": "silero",
                    "vad_pre_split_enabled": True,
                    "use_basic_filter": False,
                    "ff_chunk": 10,
                }
                self.processor._run_media_command = fake_run
                self.processor._split_with_vad = lambda *args, **kwargs: (False, [])
                self.processor._write_grouped_chunks_parallel = lambda _wav, _dir, grouped: written.extend(grouped)

                chunk_dir, vad_segments = self.processor.extract_audio(video_path)

                self.assertEqual(vad_segments, [])
                self.assertTrue(os.path.isdir(chunk_dir))
                self.assertEqual(written, [{"start": 0.0, "end": 4.0}])
            finally:
                config.OUTPUT_DIR = old_output_dir

    def test_audio_work_paths_are_scoped_by_media_fingerprint_for_same_basename(self):
        with tempfile.TemporaryDirectory() as tmp:
            path_a = os.path.join(tmp, "a", "same.mp4")
            path_b = os.path.join(tmp, "b", "same.mp4")
            os.makedirs(os.path.dirname(path_a), exist_ok=True)
            os.makedirs(os.path.dirname(path_b), exist_ok=True)
            with open(path_a, "wb") as f:
                f.write(b"first-media")
            with open(path_b, "wb") as f:
                f.write(b"second-media")

            paths_a = self.processor._audio_work_paths(path_a)
            paths_b = self.processor._audio_work_paths(path_b)

            self.assertNotEqual(paths_a["work_dir"], paths_b["work_dir"])
            self.assertNotEqual(paths_a["cleaned_wav"], paths_b["cleaned_wav"])
            self.assertTrue(paths_a["chunk_dir"].endswith("_chunks"))

    def test_selected_vad_does_not_pre_split_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_output_dir = config.OUTPUT_DIR
            config.OUTPUT_DIR = tmp
            try:
                video_path = os.path.join(tmp, "active.mp4")
                open(video_path, "wb").close()

                def write_active_wav(path: str, seconds: float = 4.0):
                    frames = int(16000 * seconds)
                    samples = [
                        int(9000 * (1 if i % 2 == 0 else -1))
                        for i in range(frames)
                    ]
                    with wave.open(path, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(16000)
                        wf.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))

                def fake_run(cmd, *, label, timeout=None):
                    if label == "ffmpeg 오디오 추출":
                        write_active_wav(cmd[-1])
                    elif "음량 평탄화" in label:
                        write_active_wav(cmd[-1])
                    return True

                written = []
                self.processor._load_all_settings = lambda: {
                    "selected_audio_ai": "none",
                    "selected_vad": "silero",
                    "vad_post_stt_align_enabled": False,
                    "use_basic_filter": False,
                    "ff_chunk": 10,
                }
                self.processor._run_media_command = fake_run
                self.processor._split_with_vad = (
                    lambda *args, **kwargs: self.fail("VAD must not pre-split STT unless opted in")
                )
                self.processor._write_grouped_chunks_parallel = lambda _wav, _dir, grouped: written.extend(grouped)

                chunk_dir, vad_segments = self.processor.extract_audio(video_path)

                self.assertEqual(vad_segments, [])
                self.assertTrue(os.path.isdir(chunk_dir))
                self.assertEqual(written, [{"start": 0.0, "end": 4.0}])
            finally:
                config.OUTPUT_DIR = old_output_dir

    def test_internal_ffmpeg_preprocess_uses_single_pass_and_reuses_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_output_dir = config.OUTPUT_DIR
            config.OUTPUT_DIR = tmp
            try:
                video_path = os.path.join(tmp, "large.mp4")
                with open(video_path, "wb") as f:
                    f.write(b"video")

                def write_active_wav(path: str, seconds: float = 4.0):
                    frames = int(16000 * seconds)
                    with wave.open(path, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(16000)
                        wf.writeframes(b"\x01\x00" * frames)

                calls = []

                def fake_run(cmd, *, label, timeout=None, env=None):
                    calls.append((label, list(cmd)))
                    write_active_wav(cmd[-1])
                    return True

                self.processor._load_all_settings = lambda: {
                    "selected_audio_ai": "none",
                    "selected_vad": "none",
                    "use_basic_filter": False,
                    "ff_chunk": 10,
                    "reuse_preprocessed_audio_cache": True,
                    "ffmpeg_filter_threads": 4,
                }
                self.processor._run_media_command = fake_run
                self.processor._write_grouped_chunks_parallel = lambda *_args, **_kwargs: None

                self.processor.extract_audio(video_path)
                self.processor.extract_audio(video_path)

                self.assertEqual([label for label, _cmd in calls], ["Mac Native Fast 음량 평탄화"])
                cmd = calls[0][1]
                self.assertIn("-filter_threads", cmd)
                self.assertIn("-threads", cmd)
                self.assertIn("-map", cmd)
                self.assertIn("0:a:0", cmd)
                self.assertIn("-vn", cmd)
                self.assertIn("-sn", cmd)
                self.assertIn("-dn", cmd)
                self.assertIn("-ar", cmd)
                self.assertIn("16000", cmd)
            finally:
                config.OUTPUT_DIR = old_output_dir

    def test_ffmpeg_progress_pipe_emits_percent_stage_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source.wav")
            target = os.path.join(tmp, "target.wav")
            with wave.open(source, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00\x00" * 16000 * 10)

            class FakeProcess:
                def __init__(self):
                    self.stdout = iter([
                        "out_time_ms=0\n",
                        "out_time_ms=5000000\n",
                        "out_time_ms=10000000\n",
                    ])
                    self.returncode = 0

                def communicate(self, timeout=None):
                    return "", ""

                def wait(self, timeout=None):
                    return self.returncode

            popen_calls = []

            def fake_popen(cmd, **kwargs):
                popen_calls.append((cmd, kwargs))
                return FakeProcess()

            stages = []
            self.processor.stage_callback = stages.append

            with patch("core.audio.media_processor_audio.subprocess.Popen", side_effect=fake_popen):
                ok = self.processor._run_media_command(
                    ["ffmpeg", "-y", "-nostdin", "-loglevel", "error", "-i", source, "-acodec", "pcm_s16le", target],
                    label="ffmpeg 음량 평탄화",
                )

            self.assertTrue(ok)
            self.assertIn("-progress", popen_calls[0][0])
            self.assertIn("pipe:1", popen_calls[0][0])
            self.assertTrue(any("0%" in stage for stage in stages))
            self.assertTrue(any("50%" in stage for stage in stages))
            self.assertTrue(any("100%" in stage for stage in stages))

    def test_ffmpeg_progress_suppresses_duplicate_percent_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source.wav")
            target = os.path.join(tmp, "target.wav")
            with wave.open(source, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00\x00" * 16000 * 10)

            class FakeProcess:
                def __init__(self):
                    self.stdout = iter([
                        "out_time_ms=0\n",
                        "out_time_ms=100000\n",
                        "out_time_ms=150000\n",
                        "out_time_ms=190000\n",
                        "out_time_ms=200000\n",
                        "out_time_ms=250000\n",
                        "out_time_ms=10000000\n",
                    ])
                    self.returncode = 0

                def wait(self, timeout=None):
                    return self.returncode

            stages = []
            self.processor.stage_callback = stages.append

            with patch("core.audio.media_processor_audio.subprocess.Popen", return_value=FakeProcess()):
                ok = self.processor._run_media_command(
                    ["ffmpeg", "-y", "-i", source, "-acodec", "pcm_s16le", target],
                    label="ffmpeg 오디오 추출",
                )

            self.assertTrue(ok)
            progress = [
                stage.rsplit(" ", 1)[-1]
                for stage in stages
                if "ffmpeg 오디오 추출 진행 중" in stage
            ]
            self.assertEqual(progress, ["0%", "1%", "2%", "99%", "100%"])
            self.assertEqual(len(progress), len(set(progress)))

    def test_vad_progress_suppresses_duplicate_bucket_updates(self):
        stages = []
        self.processor.stage_callback = stages.append

        self.processor._emit_vad_progress("TEN_VAD", "오디오 스캔", 0, force=True)
        self.processor._emit_vad_progress("TEN_VAD", "오디오 스캔", 1, step=10)
        self.processor._emit_vad_progress("TEN_VAD", "오디오 스캔", 9, step=10)
        self.processor._emit_vad_progress("TEN_VAD", "오디오 스캔", 10, step=10)
        self.processor._emit_vad_progress("TEN_VAD", "오디오 스캔", 19, step=10)
        self.processor._emit_vad_progress("TEN_VAD", "오디오 스캔", 20, step=10)
        self.processor._emit_vad_progress("TEN_VAD", "오디오 스캔", 100, force=True)

        progress = [
            stage.rsplit(" ", 1)[-1]
            for stage in stages
            if "TEN_VAD 오디오 스캔" in stage
        ]
        self.assertEqual(progress, ["0%", "10%", "20%", "100%"])

    def test_audio_heartbeat_emits_elapsed_status(self):
        logs = []
        stages = []

        class FakeStopEvent:
            def __init__(self):
                self.calls = 0
                self.stopped = False

            def wait(self, _interval):
                self.calls += 1
                return self.calls > 1

            def set(self):
                self.stopped = True

        class FakeThread:
            def __init__(self, target, **_kwargs):
                self._target = target

            def start(self):
                self._target()

            def join(self, timeout=None):
                pass

        ticks = iter([100.0, 107.0])
        self.processor.stage_callback = stages.append
        with patch("core.audio.media_processor.threading.Event", FakeStopEvent), \
             patch("core.audio.media_processor.threading.Thread", FakeThread), \
             patch("core.audio.media_processor.time.monotonic", side_effect=lambda: next(ticks)), \
             patch("core.audio.media_processor.get_logger", return_value=SimpleNamespace(log=logs.append)):
            handle = self.processor._start_audio_heartbeat("ClearVoice", "음성 향상", interval_sec=5.0)
            self.processor._stop_audio_heartbeat(handle)

        self.assertIn("⏳ [음성] ClearVoice 음성 향상 중... 7초", stages)
        self.assertIn("  └ [음성] ClearVoice 음성 향상 진행 중... 7초", logs)

    def test_resemble_enhance_wraps_model_run_with_audio_heartbeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source.wav")
            target = os.path.join(tmp, "target.wav")
            open(source, "wb").close()
            calls = []

            def fake_copy(_out_dir, out_wav):
                open(out_wav, "wb").close()
                return True

            self.processor._resolve_python_cli = lambda *_args, **_kwargs: sys.executable
            self.processor._resemble_enhance_device = lambda: "cpu"
            self.processor._run_media_command = lambda *args, **kwargs: calls.append(("run", kwargs.get("label"))) or True
            self.processor._copy_first_wav_from_dir = fake_copy
            self.processor._huggingface_env = lambda: {}
            self.processor._start_audio_heartbeat = lambda label, phase, **_kwargs: calls.append(("start", label, phase)) or ("stop", "thread")
            self.processor._stop_audio_heartbeat = lambda handle: calls.append(("stop", handle))

            self.assertTrue(self.processor._apply_resemble_enhance(source, target))

            self.assertIn(("start", "Resemble Enhance", "음성 향상"), calls)
            self.assertIn(("run", "Resemble Enhance 음성 향상"), calls)
            self.assertIn(("stop", ("stop", "thread")), calls)

    def test_long_no_vad_preprocess_extracts_stt_chunks_directly_from_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_output_dir = config.OUTPUT_DIR
            config.OUTPUT_DIR = tmp
            try:
                video_path = os.path.join(tmp, "long.mp4")
                with open(video_path, "wb") as f:
                    f.write(b"video")

                calls = []

                def write_silent_wav(path: str, seconds: float = 1.0):
                    frames = int(16000 * seconds)
                    with wave.open(path, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(16000)
                        wf.writeframes(b"\x00\x00" * frames)

                def fake_no_progress(cmd, *, label, timeout=None, env=None):
                    calls.append((label, list(cmd)))
                    write_silent_wav(cmd[-1])
                    return True

                self.processor._load_all_settings = lambda: {
                    "selected_audio_ai": "none",
                    "selected_vad": "none",
                    "vad_post_stt_align_enabled": False,
                    "use_basic_filter": False,
                    "max_speakers": 1,
                    "ff_chunk": 30,
                    "whisper_chunk_overlap_sec": 0.0,
                    "direct_ffmpeg_chunk_extract": True,
                    "direct_ffmpeg_chunk_min_sec": 10,
                }
                self.processor._media_duration_for_progress = lambda _path: 65.0
                self.processor._run_media_command_no_progress = fake_no_progress
                self.processor._run_media_command = (
                    lambda *_args, **_kwargs: self.fail("direct chunk path must not build full cleaned wav")
                )

                chunk_dir, vad_segments = self.processor.extract_audio(video_path)

                self.assertEqual(vad_segments, [])
                chunks = sorted(f for f in os.listdir(chunk_dir) if f.endswith(".wav"))
                self.assertEqual(len(chunks), 3)
                self.assertFalse(os.path.exists(os.path.join(tmp, "long_cleaned.wav")))
                self.assertEqual([label for label, _cmd in calls].count("오디오 라우팅 샘플 추출"), 3)
                self.assertEqual([label for label, _cmd in calls].count("구간별 FFMPEG 청크 추출"), 3)
                self.assertTrue(os.path.exists(os.path.join(chunk_dir, "audio_routes.json")))
                first_cmd = next(cmd for label, cmd in calls if label == "구간별 FFMPEG 청크 추출")
                self.assertIn("-ss", first_cmd)
                self.assertIn("-t", first_cmd)
                self.assertIn(video_path, first_cmd)
                self.assertIn("-map", first_cmd)
                self.assertIn("0:a:0", first_cmd)
                self.assertIn("-ar", first_cmd)
                self.assertIn("16000", first_cmd)
            finally:
                config.OUTPUT_DIR = old_output_dir

    def test_long_no_vad_direct_extract_batches_chunks_when_routing_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_output_dir = config.OUTPUT_DIR
            config.OUTPUT_DIR = tmp
            try:
                video_path = os.path.join(tmp, "long.mp4")
                with open(video_path, "wb") as f:
                    f.write(b"video")

                calls = []

                def write_silent_wav(path: str, seconds: float = 1.0):
                    frames = int(16000 * seconds)
                    with wave.open(path, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(16000)
                        wf.writeframes(b"\x00\x00" * frames)

                def fake_no_progress(cmd, *, label, timeout=None, env=None):
                    calls.append((label, list(cmd)))
                    for part in cmd:
                        if str(part).lower().endswith(".wav"):
                            write_silent_wav(str(part))
                    return True

                self.processor._load_all_settings = lambda: {
                    "selected_audio_ai": "none",
                    "selected_vad": "none",
                    "vad_post_stt_align_enabled": False,
                    "use_basic_filter": False,
                    "max_speakers": 1,
                    "ff_chunk": 30,
                    "whisper_chunk_overlap_sec": 0.0,
                    "direct_ffmpeg_chunk_extract": True,
                    "direct_ffmpeg_chunk_min_sec": 10,
                    "direct_ffmpeg_chunk_batch_extract": True,
                    "direct_ffmpeg_chunk_batch_size": 8,
                    "audio_chunk_routing_enabled": False,
                }
                self.processor._media_duration_for_progress = lambda _path: 65.0
                self.processor._run_media_command_no_progress = fake_no_progress
                self.processor._run_media_command = (
                    lambda *_args, **_kwargs: self.fail("direct batch path must not build full cleaned wav")
                )

                chunk_dir, vad_segments = self.processor.extract_audio(video_path)

                self.assertEqual(vad_segments, [])
                chunks = sorted(f for f in os.listdir(chunk_dir) if f.endswith(".wav"))
                self.assertEqual(len(chunks), 3)
                self.assertFalse(os.path.exists(os.path.join(tmp, "long_cleaned.wav")))
                self.assertEqual([label for label, _cmd in calls], ["ffmpeg 직접 청크 배치 추출"])
                cmd = calls[0][1]
                self.assertIn("-filter_complex", cmd)
                filter_graph = cmd[cmd.index("-filter_complex") + 1]
                self.assertIn("asplit=3", filter_graph)
                self.assertIn("atrim=start=0.000:end=30.000", filter_graph)
                self.assertEqual(cmd.count("-map"), 3)
                self.assertIn("-vn", cmd)
                self.assertIn("-sn", cmd)
                self.assertIn("-dn", cmd)
            finally:
                config.OUTPUT_DIR = old_output_dir

    def test_cleaned_wav_chunks_use_pcm_fast_path_without_ffmpeg_retrim(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = os.path.join(tmp, "cleaned.wav")
            chunk_dir = os.path.join(tmp, "chunks")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                frames = []
                for idx in range(16000 * 4):
                    frames.append(struct.pack("<h", idx % 32767))
                wf.writeframes(b"".join(frames))

            self.processor._load_all_settings = lambda: {"wav_pcm_fast_chunk_extract": True}
            self.processor._ffmpeg_trim_to_wav = (
                lambda *_args, **_kwargs: self.fail("PCM fast chunking should avoid ffmpeg retrim")
            )

            ok = self.processor._write_grouped_chunks_parallel(
                wav_path,
                chunk_dir,
                [{"start": 0.0, "end": 1.5}, {"start": 1.0, "end": 3.25}],
            )

            self.assertTrue(ok)
            chunks = sorted(name for name in os.listdir(chunk_dir) if name.endswith(".wav"))
            self.assertEqual(chunks, ["vad_000_0.000.wav", "vad_001_1.000.wav"])
            with wave.open(os.path.join(chunk_dir, chunks[0]), "rb") as wf:
                self.assertEqual(wf.getframerate(), 16000)
                self.assertEqual(wf.getnchannels(), 1)
                self.assertAlmostEqual(wf.getnframes() / wf.getframerate(), 1.5, places=2)
            with wave.open(os.path.join(chunk_dir, chunks[1]), "rb") as wf:
                self.assertAlmostEqual(wf.getnframes() / wf.getframerate(), 2.25, places=2)

    def test_direct_media_batch_extract_splits_sparse_chunks_by_span(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_path = os.path.join(tmp, "sparse.mp4")
            chunk_dir = os.path.join(tmp, "chunks")
            with open(media_path, "wb") as f:
                f.write(b"video")

            calls = []

            def write_silent_wav(path: str):
                with wave.open(path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(b"\x00\x00" * 16000)

            def fake_no_progress(cmd, *, label, timeout=None, env=None):
                calls.append((label, list(cmd)))
                os.makedirs(chunk_dir, exist_ok=True)
                for part in cmd:
                    if str(part).lower().endswith(".wav"):
                        write_silent_wav(str(part))
                return True

            self.processor._run_media_command_no_progress = fake_no_progress

            ok = self.processor._write_grouped_chunks_from_media_batched(
                media_path,
                chunk_dir,
                [
                    {"start": 0.0, "end": 30.0},
                    {"start": 40.0, "end": 70.0},
                    {"start": 400.0, "end": 430.0},
                ],
                "anull",
                {
                    "direct_ffmpeg_chunk_batch_size": 8,
                    "direct_ffmpeg_chunk_batch_max_span_sec": 120.0,
                },
            )

            self.assertTrue(ok)
            self.assertEqual([label for label, _cmd in calls], ["ffmpeg 직접 청크 배치 추출"] * 2)
            first_cmd = calls[0][1]
            second_cmd = calls[1][1]
            self.assertEqual(first_cmd[first_cmd.index("-t") + 1], "70.000")
            self.assertIn("asplit=2", first_cmd[first_cmd.index("-filter_complex") + 1])
            self.assertEqual(second_cmd[second_cmd.index("-ss") + 1], "400.000")
            self.assertEqual(second_cmd[second_cmd.index("-t") + 1], "30.000")
            self.assertNotIn("asplit=1", second_cmd[second_cmd.index("-filter_complex") + 1])

    def test_no_vad_fallback_chunks_restart_at_confirmed_cut_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_output_dir = config.OUTPUT_DIR
            config.OUTPUT_DIR = tmp
            try:
                video_path = os.path.join(tmp, "fallback.mp4")
                open(video_path, "wb").close()
                cleaned_wav = os.path.join(tmp, "fallback_cleaned.wav")
                with wave.open(cleaned_wav, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(b"\x00\x00" * int(16000 * 70))

                captured = {}

                self.processor._load_all_settings = lambda: {
                    "selected_audio_ai": "none",
                    "selected_vad": "none",
                    "vad_post_stt_align_enabled": False,
                    "use_basic_filter": False,
                    "max_speakers": 1,
                    "ff_chunk": 30,
                    "whisper_chunk_overlap_sec": 0.0,
                    "direct_ffmpeg_chunk_extract": False,
                }
                def fake_run(cmd, *args, **kwargs):
                    with wave.open(cmd[-1], "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(16000)
                        wf.writeframes(b"\x00\x00" * int(16000 * 70))
                    return True

                self.processor._run_media_command = fake_run
                self.processor._write_grouped_chunks_parallel = (
                    lambda _wav, _dir, grouped: captured.setdefault("grouped", [dict(row) for row in grouped])
                )
                self.processor.hard_cut_boundaries = [45.0]

                chunk_dir, vad_segments = self.processor.extract_audio(video_path, target_start_sec=20.0, target_end_sec=70.0)

                self.assertEqual(vad_segments, [])
                self.assertTrue(chunk_dir.endswith("_chunks"))
                grouped = captured.get("grouped") or []
                self.assertEqual(grouped[0], {"start": 20.0, "end": 45.0})
                self.assertEqual(grouped[1], {"start": 45.0, "end": 50.0})
                self.assertEqual(grouped[2], {"start": 50.0, "end": 70.0})
                self.assertTrue(any(abs(float(row.get("start", 0.0)) - 45.0) < 0.001 for row in grouped))
                self.assertFalse(any(float(row.get("start", 0.0)) < 45.0 < float(row.get("end", 0.0)) for row in grouped))
            finally:
                config.OUTPUT_DIR = old_output_dir

    def test_wav_activity_stats_detects_audio_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = os.path.join(tmp, "voice.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                samples = [
                    int(12000 * (1 if i % 2 == 0 else -1))
                    for i in range(16000)
                ]
                wf.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))

            stats = self.processor._wav_activity_stats(wav_path)

            self.assertAlmostEqual(stats["duration"], 1.0, places=2)
            self.assertGreater(stats["peak"], 0.3)
            self.assertGreater(stats["rms"], 0.3)

    def test_force_split_activity_threshold_matches_reported_audio(self):
        self.assertFalse(self.processor._has_force_split_activity({"peak": 0.0, "rms": 0.0}, {}))
        self.assertTrue(self.processor._has_force_split_activity({"peak": 0.8515, "rms": 0.1843}, {}))

    def test_vad_retries_with_more_sensitive_threshold_when_audio_is_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = os.path.join(tmp, "active.wav")
            chunk_dir = os.path.join(tmp, "chunks")
            os.makedirs(chunk_dir, exist_ok=True)
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                samples = [
                    int(9000 * (1 if i % 2 == 0 else -1))
                    for i in range(16000 * 4)
                ]
                wf.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))

            calls = []

            def fake_get_speech_timestamps(
                audio_data,
                model,
                *,
                sampling_rate,
                threshold,
                min_speech_duration_ms,
                min_silence_duration_ms,
                speech_pad_ms,
                window_size_samples,
            ):
                calls.append(
                    {
                        "sampling_rate": sampling_rate,
                        "threshold": threshold,
                        "min_speech": min_speech_duration_ms,
                        "min_silence": min_silence_duration_ms,
                        "pad": speech_pad_ms,
                        "window": window_size_samples,
                    }
                )
                if len(calls) < 4:
                    return []
                return [{"start": 1600, "end": 32000}]

            self.processor._vad_loaded = True
            self.processor._vad_model = object()
            self.processor._vad_utils = (
                fake_get_speech_timestamps,
                None,
                lambda _path: [0.0],
                None,
                None,
            )
            written = []
            self.processor._write_grouped_chunks_parallel = lambda _wav, _dir, grouped: written.extend(grouped)

            with patch.dict("sys.modules", {"torch": SimpleNamespace()}):
                success, timestamps = self.processor._split_with_vad(
                    wav_path,
                    chunk_dir,
                    "silero",
                    {
                        "vad_threshold": 0.55,
                        "vad_min_speech": 0.28,
                        "vad_min_silence": 1.2,
                        "vad_speech_pad": 0.1,
                        "vad_window_size": 512,
                        "review_vad_before_stt_enabled": False,
                    },
                )

            self.assertTrue(success)
            self.assertEqual(len(calls), 4)
            self.assertLess(calls[1]["threshold"], calls[0]["threshold"])
            self.assertLess(calls[2]["threshold"], calls[1]["threshold"])
            self.assertLess(calls[3]["threshold"], calls[2]["threshold"])
            self.assertLessEqual(calls[3]["min_speech"], calls[1]["min_speech"])
            self.assertLessEqual(calls[3]["min_silence"], calls[1]["min_silence"])
            self.assertEqual(timestamps[0]["start"], 0.0)
            self.assertTrue(written)
            self.assertFalse(self.processor._vad_loaded)
            self.assertIsNone(self.processor._vad_model)
            self.assertIsNone(self.processor._vad_utils)

    def test_vad_retry_rejects_noisy_micro_segments(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = os.path.join(tmp, "noisy.wav")
            chunk_dir = os.path.join(tmp, "chunks")
            os.makedirs(chunk_dir, exist_ok=True)
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                samples = [
                    int(9000 * (1 if i % 2 == 0 else -1))
                    for i in range(16000 * 4)
                ]
                wf.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))

            calls = []

            def fake_get_speech_timestamps(
                audio_data,
                model,
                *,
                sampling_rate,
                threshold,
                min_speech_duration_ms,
                min_silence_duration_ms,
                speech_pad_ms,
                window_size_samples,
            ):
                calls.append({"sampling_rate": sampling_rate, "threshold": threshold})
                if len(calls) == 1:
                    return []
                return [
                    {"start": i * 1600, "end": i * 1600 + 800}
                    for i in range(16)
                ]

            self.processor._vad_loaded = True
            self.processor._vad_model = object()
            self.processor._vad_utils = (
                fake_get_speech_timestamps,
                None,
                lambda _path: [0.0],
                None,
                None,
            )
            self.processor._write_grouped_chunks_parallel = (
                lambda *_args, **_kwargs: self.fail("Noisy micro VAD segments must be rejected")
            )

            with patch.dict("sys.modules", {"torch": SimpleNamespace()}):
                success, timestamps = self.processor._split_with_vad(
                    wav_path,
                    chunk_dir,
                    "silero",
                    {
                        "vad_threshold": 0.55,
                        "vad_min_speech": 0.28,
                        "vad_min_silence": 1.2,
                        "vad_speech_pad": 0.1,
                        "vad_window_size": 512,
                        "review_vad_before_stt_enabled": False,
                    },
                )

            self.assertFalse(success)
            self.assertEqual(timestamps, [])
            self.assertEqual(len(calls), 4)
            self.assertFalse(self.processor._vad_loaded)
            self.assertIsNone(self.processor._vad_model)
            self.assertIsNone(self.processor._vad_utils)

    def test_transcribe_releases_mlx_worker_after_completion(self):
        class _Stdout:
            def __init__(self, lines):
                self.lines = list(lines)

            def readline(self):
                return self.lines.pop(0) if self.lines else ""

        class _Proc:
            def __init__(self, lines):
                self.stdout = _Stdout(lines)

            def poll(self):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            chunk_dir = os.path.join(tmp, "chunks")
            os.makedirs(chunk_dir, exist_ok=True)
            wav_path = os.path.join(chunk_dir, "vad_000_0.000.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00\x00" * 16000)

            lines = [
                json.dumps(
                    {
                        "task_id": "task-1",
                        "index": 0,
                        "result": {
                            "segments": [
                                {"start": 0.0, "end": 0.5, "text": "테스트", "words": []}
                            ]
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n",
                json.dumps({"task_id": "task-1", "done": True}, ensure_ascii=False) + "\n",
            ]
            proc = _Proc(lines)
            stopped = []
            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "mlx-test-model",
                "w_none_temp_max": 0.0,
                "stt_ensemble_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
                "stt_persistent_runtime_reuse_enabled": False,
            }

            with patch.object(config, "IS_MAC", True), \
                 patch("core.audio.whisper_coreml.is_coreml_whisper_model", return_value=False), \
                 patch("core.audio.whisper_transformers.is_transformers_whisper_model", return_value=False), \
                 patch("core.audio.whisper_mlx.ensure_worker", return_value=proc), \
                 patch("core.audio.whisper_mlx.submit_task", return_value="task-1"), \
                 patch("core.audio.whisper_mlx.stop_worker", side_effect=lambda p: stopped.append(p)):
                rows = list(self.processor.transcribe(chunk_dir, cleanup_chunk_dir=False))

        self.assertEqual(rows[0][0][0]["text"], "테스트")
        self.assertEqual(stopped, [proc])
        self.assertIsNone(self.processor._whisper_proc)
        self.assertIsNone(self.processor._whisper_runner_proc)

    def test_transcribe_disables_word_timestamps_for_selective_fast_pass(self):
        class _Stdout:
            def __init__(self, lines):
                self.lines = list(lines)

            def readline(self):
                return self.lines.pop(0) if self.lines else ""

        class _Proc:
            def __init__(self, lines):
                self.stdout = _Stdout(lines)

            def poll(self):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            chunk_dir = os.path.join(tmp, "chunks")
            os.makedirs(chunk_dir, exist_ok=True)
            wav_path = os.path.join(chunk_dir, "vad_000_0.000.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00\x00" * 16000)

            proc = _Proc([
                json.dumps(
                    {
                        "task_id": "task-1",
                        "index": 0,
                        "word_timestamps": False,
                        "result": {
                            "segments": [{"start": 0.0, "end": 0.5, "text": "빠른 패스", "words": []}]
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n",
                json.dumps({"task_id": "task-1", "done": True}, ensure_ascii=False) + "\n",
            ])
            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "mlx-test-model",
                "w_none_temp_max": 0.0,
                "stt_ensemble_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
                "stt_npu_prefer_enabled": False,
                "stt_word_timestamps_mode": "selective",
                "stt_word_timestamps_default_enabled": False,
                "stt_word_timestamps_precision_enabled": False,
            }

            with patch.object(config, "IS_MAC", True), \
                 patch("core.audio.whisper_coreml.is_coreml_whisper_model", return_value=False), \
                 patch("core.audio.whisper_transformers.is_transformers_whisper_model", return_value=False), \
                 patch("core.audio.whisper_mlx.ensure_worker", return_value=proc), \
                 patch("core.audio.whisper_mlx.submit_task", return_value="task-1") as submit_task, \
                 patch("core.audio.whisper_mlx.stop_worker"):
                rows = list(self.processor.transcribe(chunk_dir, cleanup_chunk_dir=False))

        self.assertEqual(rows[0][0][0]["text"], "빠른 패스")
        self.assertFalse(submit_task.call_args.kwargs["word_timestamps"])
        self.assertFalse(rows[0][0][0]["asr_metadata"]["word_timestamps_requested"])

    def test_transcribe_prefers_whisperkit_route_for_npu_compatible_model(self):
        class _Stdout:
            def __init__(self, lines):
                self.lines = list(lines)

            def readline(self):
                return self.lines.pop(0) if self.lines else ""

        class _Proc:
            def __init__(self, lines):
                self.stdout = _Stdout(lines)
                self.returncode = 0

            def poll(self):
                return None

            def wait(self, timeout=None):
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            chunk_dir = os.path.join(tmp, "chunks")
            os.makedirs(chunk_dir, exist_ok=True)
            wav_path = os.path.join(chunk_dir, "vad_000_0.000.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00\x00" * 16000)

            proc = _Proc([
                json.dumps(
                    {
                        "task_id": "task-npu",
                        "index": 0,
                        "backend": "whisperkit-persistent",
                        "word_timestamps": False,
                        "result": {
                            "segments": [{"start": 0.0, "end": 0.5, "text": "NPU", "words": []}],
                            "chunk_path": wav_path,
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n",
                json.dumps({"task_id": "task-npu", "done": True}, ensure_ascii=False) + "\n",
            ])
            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "mlx-community/whisper-large-v3-mlx",
                "runtime_npu_acceleration_enabled": True,
                "stt_npu_prefer_enabled": True,
                "w_none_temp_max": 0.0,
                "stt_ensemble_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
            }

            with patch.object(config, "IS_MAC", True), \
                 patch("core.audio.npu_acceleration.apple_neural_engine_available", return_value=True), \
                 patch("core.audio.whisper_transformers.is_transformers_whisper_model", return_value=False), \
                 patch("core.audio.whisperkit_persistent.find_whisperkit_persistent_worker", return_value="/tmp/WhisperKitPersistentWorker"), \
                 patch("core.audio.whisperkit_persistent.ensure_worker", return_value=proc), \
                 patch("core.audio.whisperkit_persistent.submit_task", return_value="task-npu") as submit_task, \
                 patch("core.audio.whisperkit_persistent.stop_worker"):
                rows = list(self.processor.transcribe(chunk_dir, cleanup_chunk_dir=False))

        self.assertEqual(rows[0][0][0]["text"], "NPU")
        self.assertEqual(submit_task.call_args.kwargs["model"], "whisperkit-persistent:large-v3-v20240930_626MB")
        self.assertEqual(submit_task.call_args.kwargs["concurrent_worker_count"], 1)

    def test_whisperkit_concurrent_workers_scale_under_normal_pressure(self):
        with patch("core.audio.media_processor_transcribe._stt_memory_pressure_stage", return_value="normal"), \
             patch("core.native_resource_allocator.native_task_allocation", return_value=None):
            regular = self.processor._whisperkit_concurrent_worker_count(
                {"stt_whisperkit_concurrent_workers": 4},
                total_chunks=6,
                word_timestamps=False,
            )
            precise = self.processor._whisperkit_concurrent_worker_count(
                {
                    "stt_whisperkit_word_timestamp_concurrent_workers": 2,
                    "stt_whisperkit_precision_aggressive_gpu_enabled": False,
                },
                total_chunks=6,
                word_timestamps=True,
            )

        self.assertEqual(regular, 4)
        self.assertEqual(precise, 2)

    def test_whisperkit_recheck_uses_aggressive_native_slots_under_normal_pressure(self):
        with patch("core.audio.media_processor_transcribe._stt_memory_pressure_stage", return_value="normal"), \
             patch("core.native_resource_allocator.native_task_allocation", return_value=None):
            recheck = self.processor._whisperkit_concurrent_worker_count(
                {
                    "stt_whisperkit_concurrent_workers": 4,
                    "stt_rescue_whisper_mode": True,
                    "stt_word_timestamp_precision_pass": False,
                },
                total_chunks=10,
                word_timestamps=False,
            )

        self.assertEqual(recheck, 8)

    def test_whisperkit_recheck_native_allocator_can_raise_stt2_slots_to_full_core_max(self):
        with patch("core.audio.media_processor_transcribe._stt_memory_pressure_stage", return_value="normal"), \
             patch("core.native_resource_allocator.native_task_allocation", return_value={"workers": 10, "compute_units": "all"}) as allocator:
            recheck = self.processor._whisperkit_concurrent_worker_count(
                {
                    "benchmark_runtime_profile": "apple_m_full_core_throughput",
                    "stt_rescue_whisper_mode": True,
                    "stt_word_timestamp_precision_pass": False,
                    "stt_whisperkit_recheck_concurrent_workers": 8,
                    "stt_whisperkit_recheck_concurrent_max_workers": 10,
                    "stt_whisperkit_gpu_saturation_max_workers": 10,
                    "stt_whisperkit_native_allocator_can_raise_workers": True,
                },
                total_chunks=10,
                word_timestamps=False,
            )

        self.assertEqual(recheck, 10)
        self.assertEqual(allocator.call_args.args[0], "stt2")
        self.assertEqual(allocator.call_args.kwargs["requested_workers"], 10)
        self.assertEqual(allocator.call_args.kwargs["maximum"], 10)

    def test_whisperkit_concurrent_workers_native_allocator_can_raise_precision_slots(self):
        with patch("core.audio.media_processor_transcribe._stt_memory_pressure_stage", return_value="normal"), \
             patch("core.native_resource_allocator.native_task_allocation", return_value={"workers": 6, "compute_units": "all"}) as allocator:
            settings = {
                "stt_whisperkit_word_timestamp_concurrent_workers": 2,
                "stt_whisperkit_concurrent_max_workers": 4,
                "stt_whisperkit_native_allocator_can_raise_workers": True,
                "stt_whisperkit_precision_aggressive_gpu_enabled": False,
                "stt_whisperkit_compute_profile": "auto",
            }
            precise = self.processor._whisperkit_concurrent_worker_count(
                settings,
                total_chunks=8,
                word_timestamps=True,
            )
            compute_profile = self.processor._whisperkit_compute_profile(
                settings,
                word_timestamps=True,
            )

        self.assertEqual(precise, 6)
        self.assertEqual(compute_profile, "all")
        self.assertEqual(allocator.call_args.kwargs["task"] if "task" in allocator.call_args.kwargs else allocator.call_args.args[0], "stt_precision")

    def test_whisperkit_compute_profile_keeps_explicit_override(self):
        self.processor._whisperkit_native_allocation_plan = {
            "chunks": 8,
            "word_timestamps": True,
            "task": "stt_precision",
            "plan": {"compute_units": "all"},
        }

        compute_profile = self.processor._whisperkit_compute_profile(
            {"stt_whisperkit_compute_profile": "gpu"},
            word_timestamps=True,
        )

        self.assertEqual(compute_profile, "gpu")

    def test_whisperkit_precision_aggressive_gpu_raises_slots_under_normal_pressure(self):
        with patch("core.audio.media_processor_transcribe._stt_memory_pressure_stage", return_value="normal"), \
             patch("core.native_resource_allocator.native_task_allocation", return_value=None):
            precise = self.processor._whisperkit_concurrent_worker_count(
                {
                    "stt_whisperkit_word_timestamp_concurrent_workers": 2,
                    "stt_whisperkit_concurrent_max_workers": 4,
                    "stt_whisperkit_gpu_saturation_max_workers": 8,
                    "stt_whisperkit_precision_aggressive_gpu_enabled": True,
                },
                total_chunks=8,
                word_timestamps=True,
            )

        self.assertEqual(precise, 8)

    def test_stt_worker_silence_timeout_prefers_word_precision_budget(self):
        timeout = self.processor._stt_worker_silence_timeout_sec(
            {
                "stt_worker_response_timeout_sec": 120.0,
                "stt_word_timestamp_worker_response_timeout_sec": 0.2,
                "stt_word_timestamp_precision_pass": True,
            },
            log_label="STT-단어정밀",
            word_timestamps=True,
        )

        self.assertEqual(timeout, 0.2)

    def test_read_worker_stdout_line_raises_when_worker_stalls(self):
        from core.audio.media_processor_transcribe import SttWorkerTimeout

        read_fd, write_fd = os.pipe()
        stream = os.fdopen(read_fd, "r", encoding="utf-8")

        class _Proc:
            stdout = stream

            def poll(self):
                return None

        try:
            with self.assertRaises(SttWorkerTimeout):
                self.processor._read_worker_stdout_line(
                    _Proc(),
                    log_label="STT-단어정밀",
                    received=31,
                    total=32,
                    wait_started_at=time.monotonic() - 1.0,
                    last_wait_log_at=time.monotonic(),
                    max_silence_sec=0.05,
                )
        finally:
            stream.close()
            os.close(write_fd)

    def test_whisperkit_submit_task_sends_batch_concurrency(self):
        from core.audio.whisperkit_persistent import submit_task

        class _Stdin:
            def __init__(self):
                self.lines = []

            def write(self, line):
                self.lines.append(line)

            def flush(self):
                pass

        class _Proc:
            def __init__(self):
                self.stdin = _Stdin()

            def poll(self):
                return None

        proc = _Proc()
        submit_task(
            proc,
            ["/tmp/a.wav", "/tmp/b.wav", "/tmp/c.wav"],
            "whisperkit-persistent:large-v3-v20240930_626MB",
            "ko",
            [0.0],
            word_timestamps=False,
            concurrent_worker_count=3,
            stream_results=True,
            compute_profile="ane_gpu",
        )

        payload = json.loads(proc.stdin.lines[0])
        self.assertEqual(payload["concurrent_worker_count"], 3)
        self.assertTrue(payload["stream_results"])
        self.assertEqual(payload["compute_profile"], "ane_gpu")
        self.assertEqual(payload["chunk_paths"], ["/tmp/a.wav", "/tmp/b.wav", "/tmp/c.wav"])

    def test_transcribe_can_route_to_experimental_whisperkit_persistent_backend(self):
        class _Stdout:
            def __init__(self, lines):
                self.lines = list(lines)

            def readline(self):
                return self.lines.pop(0) if self.lines else ""

        class _Proc:
            def __init__(self, lines):
                self.stdout = _Stdout(lines)
                self.returncode = 0

            def poll(self):
                return None

            def wait(self, timeout=None):
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            chunk_dir = os.path.join(tmp, "chunks")
            os.makedirs(chunk_dir, exist_ok=True)
            wav_path = os.path.join(chunk_dir, "vad_000_0.000.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00\x00" * 16000)

            proc = _Proc([
                json.dumps(
                    {
                        "task_id": "task-1",
                        "index": 0,
                        "backend": "whisperkit-persistent",
                        "word_timestamps": False,
                        "result": {
                            "segments": [{"start": 0.0, "end": 0.5, "text": "Swift", "words": []}],
                            "chunk_path": wav_path,
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n",
                json.dumps({"task_id": "task-1", "done": True}, ensure_ascii=False) + "\n",
            ])
            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "whisperkit-persistent:large-v3",
                "w_none_temp_max": 0.0,
                "stt_ensemble_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
                "stt_npu_prefer_enabled": False,
                "stt_word_timestamps_mode": "selective",
                "stt_word_timestamps_default_enabled": False,
                "stt_word_timestamps_precision_enabled": False,
            }

            with patch.object(config, "IS_MAC", True), \
                 patch("core.audio.whisper_coreml.is_coreml_whisper_model", return_value=False), \
                 patch("core.audio.whisper_transformers.is_transformers_whisper_model", return_value=False), \
                 patch("core.audio.whisperkit_persistent.ensure_worker", return_value=proc) as ensure_worker, \
                 patch("core.audio.whisperkit_persistent.submit_task", return_value="task-1") as submit_task, \
                 patch("core.audio.whisperkit_persistent.stop_worker"):
                rows = list(self.processor.transcribe(chunk_dir, cleanup_chunk_dir=False))

        self.assertEqual(rows[0][0][0]["text"], "Swift")
        self.assertIs(ensure_worker.return_value, proc)
        self.assertEqual(submit_task.call_args.kwargs["model"], "whisperkit-persistent:large-v3-v20240930_626MB")
        self.assertFalse(submit_task.call_args.kwargs["word_timestamps"])
        self.assertTrue(submit_task.call_args.kwargs["stream_results"])
        self.assertEqual(submit_task.call_args.kwargs["compute_profile"], "ane_gpu")

    def test_whisperkit_recheck_submits_long_chunks_first_but_emits_chronologically(self):
        class _Stdout:
            def __init__(self, lines):
                self.lines = list(lines)

            def readline(self):
                return self.lines.pop(0) if self.lines else ""

        class _Proc:
            def __init__(self, lines):
                self.stdout = _Stdout(lines)
                self.returncode = 0

            def poll(self):
                return None

            def wait(self, timeout=None):
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            chunk_dir = os.path.join(tmp, "chunks")
            os.makedirs(chunk_dir, exist_ok=True)
            wav0 = os.path.join(chunk_dir, "vad_000_0.000.wav")
            wav1 = os.path.join(chunk_dir, "vad_001_1.000.wav")
            wav2 = os.path.join(chunk_dir, "vad_002_5.000.wav")
            self._write_silent_wav(wav0, frames=16000)
            self._write_silent_wav(wav1, frames=64000)
            self._write_silent_wav(wav2, frames=32000)
            proc = _Proc([
                json.dumps(
                    {
                        "task_id": "task-duration",
                        "index": 0,
                        "backend": "whisperkit-persistent",
                        "word_timestamps": False,
                        "result": {"segments": [{"start": 0.0, "end": 0.5, "text": "긴 원본1", "words": []}]},
                    },
                    ensure_ascii=False,
                )
                + "\n",
                json.dumps(
                    {
                        "task_id": "task-duration",
                        "index": 1,
                        "backend": "whisperkit-persistent",
                        "word_timestamps": False,
                        "result": {"segments": [{"start": 0.0, "end": 0.5, "text": "중간 원본2", "words": []}]},
                    },
                    ensure_ascii=False,
                )
                + "\n",
                json.dumps(
                    {
                        "task_id": "task-duration",
                        "index": 2,
                        "backend": "whisperkit-persistent",
                        "word_timestamps": False,
                        "result": {"segments": [{"start": 0.0, "end": 0.5, "text": "짧은 원본0", "words": []}]},
                    },
                    ensure_ascii=False,
                )
                + "\n",
                json.dumps({"task_id": "task-duration", "done": True}, ensure_ascii=False) + "\n",
            ])
            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "whisperkit-persistent:large-v3",
                "w_none_temp_max": 0.0,
                "stt_ensemble_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
                "stt_rescue_whisper_mode": True,
                "stt_duration_first_submission_enabled": True,
                "stt_word_timestamps_mode": "off",
                "stt_word_timestamps_default_enabled": False,
                "stt_word_timestamps_precision_enabled": False,
            }

            with patch.object(config, "IS_MAC", True), \
                 patch("core.audio.whisper_coreml.is_coreml_whisper_model", return_value=False), \
                 patch("core.audio.whisper_transformers.is_transformers_whisper_model", return_value=False), \
                 patch("core.audio.whisperkit_persistent.ensure_worker", return_value=proc), \
                 patch("core.audio.whisperkit_persistent.submit_task", return_value="task-duration") as submit_task, \
                 patch("core.audio.whisperkit_persistent.stop_worker"):
                rows = list(self.processor.transcribe(chunk_dir, cleanup_chunk_dir=False, log_label="Fast-STT2"))

        submitted = submit_task.call_args.kwargs["chunk_paths"]
        self.assertEqual([os.path.realpath(path) for path in submitted], [os.path.realpath(path) for path in [wav1, wav2, wav0]])
        self.assertEqual([row[0][0]["text"] for row in rows], ["짧은 원본0", "긴 원본1", "중간 원본2"])
        self.assertEqual([round(row[0][0]["start"], 3) for row in rows], [0.0, 1.0, 5.0])

    def test_word_precision_straggler_skips_last_chunk_and_keeps_pipeline_moving(self):
        read_fd, write_fd = os.pipe()
        stream = os.fdopen(read_fd, "r", encoding="utf-8")

        class _Proc:
            stdout = stream
            returncode = 0

            def poll(self):
                return None

            def wait(self, timeout=None):
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            chunk_dir = os.path.join(tmp, "chunks")
            os.makedirs(chunk_dir, exist_ok=True)
            wav0 = os.path.join(chunk_dir, "vad_000_0.000.wav")
            wav1 = os.path.join(chunk_dir, "vad_001_1.000.wav")
            self._write_silent_wav(wav0)
            self._write_silent_wav(wav1)
            os.write(
                write_fd,
                (
                    json.dumps(
                        {
                            "task_id": "task-precision",
                            "index": 0,
                            "backend": "whisperkit-persistent",
                            "word_timestamps": True,
                            "result": {
                                "segments": [{"start": 0.0, "end": 0.5, "text": "정상", "words": []}],
                                "chunk_path": wav0,
                            },
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                ).encode("utf-8"),
            )
            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "whisperkit-persistent:large-v3",
                "w_none_temp_max": 0.0,
                "stt_ensemble_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
                "stt_word_timestamp_precision_pass": True,
                "stt_word_timestamps_mode": "always",
                "stt_word_timestamps_default_enabled": True,
                "stt_word_timestamps_precision_enabled": True,
                "stt_word_timestamp_worker_response_timeout_sec": 5.0,
                "stt_word_timestamp_worker_straggler_max_missing_chunks": 1,
                "stt_word_timestamp_straggler_skip_enabled": True,
            }

            try:
                with patch.object(config, "IS_MAC", True), \
                     patch("core.audio.whisper_coreml.is_coreml_whisper_model", return_value=False), \
                     patch("core.audio.whisper_transformers.is_transformers_whisper_model", return_value=False), \
                     patch("core.audio.whisperkit_persistent.ensure_worker", return_value=_Proc()), \
                     patch("core.audio.whisperkit_persistent.submit_task", return_value="task-precision"), \
                     patch("core.audio.whisperkit_persistent.stop_worker"), \
                     patch.object(self.processor, "_stt_precision_straggler_timeout_sec", return_value=0.05):
                    rows = list(self.processor.transcribe(chunk_dir, cleanup_chunk_dir=False, log_label="STT-단어정밀"))
            finally:
                stream.close()
                os.close(write_fd)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0][0]["text"], "정상")
        self.assertEqual(rows[1][0], [])

    def test_word_precision_straggler_ratio_skips_tail_and_keeps_pipeline_moving(self):
        from core.audio.media_processor_transcribe import SttWorkerTimeout

        class _Proc:
            returncode = 0

            def poll(self):
                return None

            def wait(self, timeout=None):
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            chunk_dir = os.path.join(tmp, "chunks")
            os.makedirs(chunk_dir, exist_ok=True)
            wav_paths = []
            for idx in range(10):
                path = os.path.join(chunk_dir, f"vad_{idx:03d}_{idx:.3f}.wav")
                self._write_silent_wav(path)
                wav_paths.append(path)
            worker_lines = []
            for idx in range(8):
                worker_lines.append(
                    json.dumps(
                        {
                            "task_id": "task-precision-ratio",
                            "index": idx,
                            "backend": "whisperkit-persistent",
                            "word_timestamps": True,
                            "result": {
                                "segments": [{"start": float(idx), "end": float(idx) + 0.5, "text": f"정밀{idx}", "words": []}],
                                "chunk_path": wav_paths[idx],
                            },
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "whisperkit-persistent:large-v3",
                "w_none_temp_max": 0.0,
                "stt_ensemble_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
                "stt_word_timestamp_precision_pass": True,
                "stt_word_timestamps_mode": "always",
                "stt_word_timestamps_default_enabled": True,
                "stt_word_timestamps_precision_enabled": True,
                "stt_word_timestamp_worker_response_timeout_sec": 5.0,
                "stt_word_timestamp_worker_straggler_max_missing_chunks": 1,
                "stt_word_timestamp_worker_straggler_min_received_ratio": 0.8,
                "stt_word_timestamp_straggler_skip_enabled": True,
            }

            def fake_read_worker_stdout_line(_proc, **kwargs):
                if worker_lines:
                    return worker_lines.pop(0), kwargs.get("last_wait_log_at", time.monotonic())
                raise SttWorkerTimeout("precision ratio straggler")

            with patch.object(config, "IS_MAC", True), \
                 patch("core.audio.whisper_coreml.is_coreml_whisper_model", return_value=False), \
                 patch("core.audio.whisper_transformers.is_transformers_whisper_model", return_value=False), \
                 patch("core.audio.whisperkit_persistent.ensure_worker", return_value=_Proc()), \
                 patch("core.audio.whisperkit_persistent.submit_task", return_value="task-precision-ratio"), \
                 patch("core.audio.whisperkit_persistent.stop_worker"), \
                 patch("core.audio.media_processor_transcribe.whisperkit_empty_result_fallback_model") as empty_fallback, \
                 patch.object(self.processor, "_stt_precision_straggler_timeout_sec", return_value=0.05), \
                 patch.object(self.processor, "_read_worker_stdout_line", side_effect=fake_read_worker_stdout_line):
                rows = list(self.processor.transcribe(chunk_dir, cleanup_chunk_dir=False, log_label="STT-단어정밀"))

        self.assertEqual(len(rows), 10)
        self.assertEqual([row[0][0]["text"] for row in rows[:8]], [f"정밀{idx}" for idx in range(8)])
        self.assertEqual([row[0] for row in rows[8:]], [[], []])
        empty_fallback.assert_not_called()

    def test_stt_recheck_straggler_skips_remaining_chunks_without_full_fallback(self):
        read_fd, write_fd = os.pipe()
        stream = os.fdopen(read_fd, "r", encoding="utf-8")

        class _Proc:
            stdout = stream
            returncode = 0

            def poll(self):
                return None

            def wait(self, timeout=None):
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            chunk_dir = os.path.join(tmp, "chunks")
            os.makedirs(chunk_dir, exist_ok=True)
            wav_paths = []
            for idx in range(4):
                path = os.path.join(chunk_dir, f"vad_{idx:03d}_{idx:.3f}.wav")
                self._write_silent_wav(path)
                wav_paths.append(path)
            os.write(
                write_fd,
                (
                    json.dumps(
                        {
                            "task_id": "task-recheck",
                            "index": 0,
                            "backend": "whisperkit-persistent",
                            "word_timestamps": False,
                            "result": {
                                "segments": [{"start": 0.0, "end": 0.5, "text": "보강", "words": []}],
                                "chunk_path": wav_paths[0],
                            },
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                ).encode("utf-8"),
            )
            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "whisperkit-persistent:large-v3",
                "w_none_temp_max": 0.0,
                "stt_ensemble_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
                "stt_rescue_whisper_mode": True,
                "stt_word_timestamp_precision_pass": False,
                "stt_word_timestamps_mode": "off",
                "stt_word_timestamps_default_enabled": False,
                "stt_word_timestamps_precision_enabled": False,
                "stt_worker_response_timeout_sec": 5.0,
                "stt_recheck_worker_straggler_max_missing_chunks": 4,
                "stt_recheck_straggler_skip_enabled": True,
            }

            try:
                with patch.object(config, "IS_MAC", True), \
                     patch("core.audio.whisper_coreml.is_coreml_whisper_model", return_value=False), \
                     patch("core.audio.whisper_transformers.is_transformers_whisper_model", return_value=False), \
                     patch("core.audio.whisperkit_persistent.ensure_worker", return_value=_Proc()), \
                     patch("core.audio.whisperkit_persistent.submit_task", return_value="task-recheck"), \
                     patch("core.audio.whisperkit_persistent.stop_worker"), \
                     patch("core.audio.media_processor_transcribe.whisperkit_empty_result_fallback_model") as empty_fallback, \
                     patch.object(self.processor, "_stt_recheck_straggler_timeout_sec", return_value=0.05):
                    rows = list(self.processor.transcribe(chunk_dir, cleanup_chunk_dir=False, log_label="Fast-STT2"))
            finally:
                stream.close()
                os.close(write_fd)

        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0][0][0]["text"], "보강")
        self.assertEqual([row[0] for row in rows[1:]], [[], [], []])
        empty_fallback.assert_not_called()

    def test_stt_recheck_straggler_ratio_skips_tail_without_full_fallback(self):
        from core.audio.media_processor_transcribe import SttWorkerTimeout

        class _Proc:
            returncode = 0

            def poll(self):
                return None

            def wait(self, timeout=None):
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            chunk_dir = os.path.join(tmp, "chunks")
            os.makedirs(chunk_dir, exist_ok=True)
            wav_paths = []
            for idx in range(10):
                path = os.path.join(chunk_dir, f"vad_{idx:03d}_{idx:.3f}.wav")
                self._write_silent_wav(path)
                wav_paths.append(path)
            payload_lines = []
            for idx in range(6):
                payload_lines.append(
                    json.dumps(
                        {
                            "task_id": "task-recheck-ratio",
                            "index": idx,
                            "backend": "whisperkit-persistent",
                            "word_timestamps": False,
                            "result": {
                                "segments": [{"start": float(idx), "end": float(idx) + 0.5, "text": f"보강{idx}", "words": []}],
                                "chunk_path": wav_paths[idx],
                            },
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "whisperkit-persistent:large-v3",
                "w_none_temp_max": 0.0,
                "stt_ensemble_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
                "stt_rescue_whisper_mode": True,
                "stt_word_timestamp_precision_pass": False,
                "stt_word_timestamps_mode": "off",
                "stt_word_timestamps_default_enabled": False,
                "stt_word_timestamps_precision_enabled": False,
                "stt_worker_response_timeout_sec": 5.0,
                "stt_recheck_worker_straggler_max_missing_chunks": 3,
                "stt_recheck_worker_straggler_min_received_ratio": 0.6,
                "stt_recheck_straggler_skip_enabled": True,
            }
            worker_lines = list(payload_lines)

            def fake_read_worker_stdout_line(_proc, **kwargs):
                if worker_lines:
                    return worker_lines.pop(0), kwargs.get("last_wait_log_at", time.monotonic())
                raise SttWorkerTimeout("ratio straggler")

            with patch.object(config, "IS_MAC", True), \
                 patch("core.audio.whisper_coreml.is_coreml_whisper_model", return_value=False), \
                 patch("core.audio.whisper_transformers.is_transformers_whisper_model", return_value=False), \
                 patch("core.audio.whisperkit_persistent.ensure_worker", return_value=_Proc()), \
                 patch("core.audio.whisperkit_persistent.submit_task", return_value="task-recheck-ratio"), \
                 patch("core.audio.whisperkit_persistent.stop_worker"), \
                 patch("core.audio.media_processor_transcribe.whisperkit_empty_result_fallback_model") as empty_fallback, \
                 patch.object(self.processor, "_stt_recheck_straggler_timeout_sec", return_value=0.05), \
                 patch.object(self.processor, "_read_worker_stdout_line", side_effect=fake_read_worker_stdout_line):
                rows = list(self.processor.transcribe(chunk_dir, cleanup_chunk_dir=False, log_label="Fast-STT2"))

        self.assertEqual(len(rows), 10)
        self.assertEqual([row[0][0]["text"] for row in rows[:6]], [f"보강{idx}" for idx in range(6)])
        self.assertEqual([row[0] for row in rows[6:]], [[], [], [], []])
        empty_fallback.assert_not_called()

    def test_transcribe_falls_back_to_mlx_when_whisperkit_returns_no_chunks(self):
        class _Stdout:
            def __init__(self, lines):
                self.lines = list(lines)

            def readline(self):
                return self.lines.pop(0) if self.lines else ""

        class _Proc:
            def __init__(self, lines):
                self.stdout = _Stdout(lines)
                self.returncode = 0

            def poll(self):
                return None

            def wait(self, timeout=None):
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            chunk_dir = os.path.join(tmp, "chunks")
            os.makedirs(chunk_dir, exist_ok=True)
            wav_path = os.path.join(chunk_dir, "vad_000_0.000.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00\x00" * 16000)

            empty_swift_proc = _Proc([
                json.dumps({"task_id": "task-empty", "done": True}, ensure_ascii=False) + "\n",
            ])
            mlx_proc = _Proc([
                json.dumps(
                    {
                        "task_id": "task-mlx",
                        "index": 0,
                        "result": {
                            "segments": [{"start": 0.0, "end": 0.5, "text": "재시도 성공", "words": []}]
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n",
                json.dumps({"task_id": "task-mlx", "done": True}, ensure_ascii=False) + "\n",
            ])
            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "whisperkit-persistent:large-v3",
                "w_none_temp_max": 0.0,
                "stt_ensemble_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
                "stt_word_timestamps_mode": "off",
                "stt_word_timestamps_default_enabled": False,
                "stt_word_timestamps_precision_enabled": False,
                "stt_persistent_runtime_reuse_enabled": False,
            }

            with patch.object(config, "IS_MAC", True), \
                 patch("core.audio.whisper_coreml.is_coreml_whisper_model", return_value=False), \
                 patch("core.audio.whisper_transformers.is_transformers_whisper_model", return_value=False), \
                 patch("core.audio.whisperkit_persistent.ensure_worker", return_value=empty_swift_proc), \
                 patch("core.audio.whisperkit_persistent.submit_task", return_value="task-empty"), \
                 patch("core.audio.whisperkit_persistent.stop_worker"), \
                 patch("core.audio.whisper_mlx.ensure_worker", return_value=mlx_proc), \
                 patch("core.audio.whisper_mlx.submit_task", return_value="task-mlx"), \
                 patch("core.audio.whisper_mlx.stop_worker"):
                rows = list(self.processor.transcribe(chunk_dir, cleanup_chunk_dir=False))

        self.assertEqual(rows[0][0][0]["text"], "재시도 성공")

    def test_transcribe_can_route_to_whisper_cpp_backend(self):
        class _Stdout:
            def __init__(self, lines):
                self.lines = list(lines)

            def readline(self):
                return self.lines.pop(0) if self.lines else ""

        class _Proc:
            def __init__(self, lines):
                self.stdout = _Stdout(lines)
                self.returncode = 0

            def poll(self):
                return None

            def wait(self, timeout=None):
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            chunk_dir = os.path.join(tmp, "chunks")
            os.makedirs(chunk_dir, exist_ok=True)
            wav_path = os.path.join(chunk_dir, "vad_000_0.000.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00\x00" * 16000)

            proc = _Proc([
                json.dumps(
                    {
                        "backend": "whisper.cpp",
                        "word_timestamps": False,
                        "segments": [{"start": 0.0, "end": 0.5, "text": "CPP", "words": []}],
                        "chunk_path": wav_path,
                    },
                    ensure_ascii=False,
                )
                + "\n",
            ])
            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "large-v3-turbo",
                "stt_backend_policy": "native",
                "w_none_temp_max": 0.0,
                "stt_ensemble_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
                "stt_word_timestamps_mode": "selective",
                "stt_word_timestamps_default_enabled": False,
                "stt_word_timestamps_precision_enabled": False,
            }

            with patch.object(config, "IS_MAC", True), \
                 patch("core.audio.stt_backend_router._whisper_cpp_ready", return_value=True), \
                 patch("core.audio.stt_backend_router._whisperkit_ready", return_value=False), \
                 patch("core.audio.whisper_coreml.is_coreml_whisper_model", return_value=False), \
                 patch("core.audio.whisper_transformers.is_transformers_whisper_model", return_value=False), \
                 patch("core.audio.whisper_cpp.run_whisper", return_value=proc) as run_cpp:
                rows = list(self.processor.transcribe(chunk_dir, cleanup_chunk_dir=False))

        self.assertEqual(rows[0][0][0]["text"], "CPP")
        self.assertEqual(run_cpp.call_args.kwargs["model"], "whisper.cpp:large-v3-turbo")
        self.assertFalse(run_cpp.call_args.kwargs["word_timestamps"])
        self.assertEqual(rows[0][0][0]["asr_metadata"]["backend"], "whisper.cpp")
        self.assertFalse(rows[0][0][0]["asr_metadata"]["word_timestamps_requested"])

    def test_transcribe_falls_back_from_transformers_model_when_runtime_is_unavailable(self):
        class _Stdout:
            def __init__(self, lines):
                self.lines = list(lines)

            def readline(self):
                return self.lines.pop(0) if self.lines else ""

        class _Proc:
            def __init__(self, lines):
                self.stdout = _Stdout(lines)

            def poll(self):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            chunk_dir = os.path.join(tmp, "chunks")
            os.makedirs(chunk_dir, exist_ok=True)
            wav_path = os.path.join(chunk_dir, "vad_000_0.000.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00\x00" * 16000)

            proc = _Proc(
                [
                    json.dumps(
                        {
                            "task_id": "task-1",
                            "index": 0,
                            "result": {
                                "segments": [{"start": 0.0, "end": 0.5, "text": "fallback", "words": []}],
                            },
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    json.dumps({"task_id": "task-1", "done": True}, ensure_ascii=False) + "\n",
                ]
            )
            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "o0dimplz0o/Whisper-Large-v3-turbo-STT-Zeroth-KO-v2",
                "w_none_temp_max": 0.0,
                "stt_ensemble_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
            }

            with patch.object(config, "IS_MAC", True), \
                 patch("core.audio.whisper_transformers.transformers_whisper_runtime_status", return_value=(False, "disabled")), \
                 patch(
                     "core.audio.whisper_transformers.transformers_whisper_fallback_model",
                     return_value="mlx-community/whisper-large-v3-turbo",
                 ), \
                 patch("core.audio.whisper_mlx.ensure_worker", return_value=proc), \
                 patch("core.audio.whisper_mlx.submit_task", return_value="task-1"), \
                 patch("core.audio.whisper_mlx.stop_worker"):
                rows = list(self.processor.transcribe(chunk_dir, cleanup_chunk_dir=False))

        self.assertEqual(rows[0][0][0]["text"], "fallback")

    def test_mac_worker_results_are_emitted_in_chunk_index_order(self):
        class _Stdout:
            def __init__(self, lines):
                self.lines = list(lines)

            def readline(self):
                return self.lines.pop(0) if self.lines else ""

        class _Proc:
            def __init__(self, lines):
                self.stdout = _Stdout(lines)
                self.returncode = 0

            def poll(self):
                return None

            def wait(self, timeout=None):
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            chunk_dir = os.path.join(tmp, "chunks")
            os.makedirs(chunk_dir, exist_ok=True)
            wav_paths = [
                os.path.join(chunk_dir, "vad_000_0.000.wav"),
                os.path.join(chunk_dir, "vad_001_10.000.wav"),
            ]
            for wav_path in wav_paths:
                with wave.open(wav_path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(b"\x00\x00" * 16000)

            proc = _Proc(
                [
                    json.dumps(
                        {
                            "task_id": "task-1",
                            "index": 1,
                            "result": {
                                "segments": [{"start": 0.0, "end": 0.5, "text": "뒤", "words": []}],
                                "chunk_path": wav_paths[1],
                            },
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    json.dumps(
                        {
                            "task_id": "task-1",
                            "index": 0,
                            "result": {
                                "segments": [{"start": 0.0, "end": 0.5, "text": "앞", "words": []}],
                                "chunk_path": wav_paths[0],
                            },
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    json.dumps({"task_id": "task-1", "done": True}, ensure_ascii=False) + "\n",
                ]
            )
            self.processor._load_all_settings = lambda: {
                "selected_whisper_model": "mlx-community/whisper-large-v3-turbo",
                "w_none_temp_max": 0.0,
                "stt_ensemble_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
                "stt_npu_prefer_enabled": False,
                "stt_word_timestamps_mode": "selective",
                "stt_word_timestamps_default_enabled": False,
                "stt_word_timestamps_precision_enabled": False,
            }

            with patch.object(config, "IS_MAC", True), \
                 patch("core.audio.whisper_coreml.is_coreml_whisper_model", return_value=False), \
                 patch("core.audio.whisper_transformers.is_transformers_whisper_model", return_value=False), \
                 patch("core.audio.whisper_mlx.ensure_worker", return_value=proc), \
                 patch("core.audio.whisper_mlx.submit_task", return_value="task-1"), \
                 patch("core.audio.whisper_mlx.stop_worker"):
                rows = list(self.processor.transcribe(chunk_dir, cleanup_chunk_dir=False))

        self.assertEqual([row[1] for row in rows], [1, 2])
        self.assertEqual([row[0][0]["text"] for row in rows], ["앞", "뒤"])

    def test_dash_mlx_whisper_model_is_scheduled_as_gpu(self):
        accel = self.processor._whisper_runtime_accelerator(
            "youngouk/ghost613-turbo-korean-4bit-mlx",
            {},
        )

        self.assertEqual(accel, "gpu")

    def test_whisperkit_persistent_model_is_scheduled_as_npu(self):
        accel = self.processor._whisper_runtime_accelerator(
            "whisperkit-persistent:large-v3-v20240930_626MB",
            {},
        )

        self.assertEqual(accel, "npu")


if __name__ == "__main__":
    unittest.main()
