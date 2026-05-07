import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from core.audio import stt_vad
from core.audio.media_processor import VideoProcessor
from core.pipeline.cut_boundary_helpers import PipelineCutBoundaryMixin
from core.personalization.lora_models import TruthTableRow
from core.personalization.lora_storage import append_truth_table_rows, initialize_lora_personalization_store
from core.personalization.lora_vector_retriever import retrieve_lora_context
from core.runtime import config
from ui.timeline.timeline_waveform import load_waveform_cache, save_waveform_cache, waveform_cache_path


class _CutCacheOwner(PipelineCutBoundaryMixin):
    def __init__(self):
        self.emitted = []
        self.counts = []

    def _ui_emit(self, *args):
        self.emitted.append(args)

    def _emit_cut_boundary_count_to_sidebar(self, count, *, done=False):
        self.counts.append((count, done))


class FingerprintCacheTests(unittest.TestCase):
    def test_audio_cache_config_changes_when_same_path_media_is_replaced(self):
        processor = VideoProcessor()
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, "same.mp4")
            with open(media, "wb") as handle:
                handle.write(b"first media payload")
            first = processor._audio_cache_config(
                media,
                {"ffmpeg_filter_threads": 2},
                audio_ai="none",
                use_basic=False,
                master_filter="anull",
                active_filter="anull",
            )

            with open(media, "wb") as handle:
                handle.write(b"second media payload with different bytes")
            second = processor._audio_cache_config(
                media,
                {"ffmpeg_filter_threads": 2},
                audio_ai="none",
                use_basic=False,
                master_filter="anull",
                active_filter="anull",
            )

        self.assertIn("source_fingerprint_digest", first)
        self.assertNotEqual(first["source_fingerprint_digest"], second["source_fingerprint_digest"])

    def test_cut_boundary_cache_path_uses_media_fingerprint(self):
        owner = _CutCacheOwner()
        old_output_dir = config.OUTPUT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            config.OUTPUT_DIR = tmp
            try:
                media = os.path.join(tmp, "same.mp4")
                with open(media, "wb") as handle:
                    handle.write(b"first")
                first_path = owner._cut_boundary_cache_path_for_start([media], {})

                with open(media, "wb") as handle:
                    handle.write(b"second content")
                second_path = owner._cut_boundary_cache_path_for_start([media], {})
            finally:
                config.OUTPUT_DIR = old_output_dir

        self.assertNotEqual(first_path, second_path)

    def test_cut_boundary_cache_path_uses_compare_resolution(self):
        owner = _CutCacheOwner()
        old_output_dir = config.OUTPUT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            config.OUTPUT_DIR = tmp
            try:
                media = os.path.join(tmp, "same.mp4")
                with open(media, "wb") as handle:
                    handle.write(b"media")
                default_path = owner._cut_boundary_cache_path_for_start([media], {})
                low_res_path = owner._cut_boundary_cache_path_for_start(
                    [media],
                    {"scan_cut_compare_max_width": 1280, "scan_cut_compare_max_height": 720},
                )
            finally:
                config.OUTPUT_DIR = old_output_dir

        self.assertNotEqual(default_path, low_res_path)

    def test_cut_boundary_cache_reuses_empty_result_as_completed_hit(self):
        owner = _CutCacheOwner()
        old_output_dir = config.OUTPUT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            config.OUTPUT_DIR = tmp
            try:
                media = os.path.join(tmp, "no-cuts.mp4")
                with open(media, "wb") as handle:
                    handle.write(b"steady shot")

                owner._save_cut_boundary_cache_for_start([media], {}, [])
                cached = owner._load_cut_boundary_cache_for_start("", [media], {})
            finally:
                config.OUTPUT_DIR = old_output_dir

        self.assertEqual(cached, [])
        self.assertEqual(owner.counts[-1], (0, True))

    def test_vad_timestamp_cache_invalidates_when_wav_is_replaced(self):
        processor = VideoProcessor()
        old_output_dir = config.OUTPUT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            config.OUTPUT_DIR = tmp
            try:
                wav = os.path.join(tmp, "sample.wav")
                with open(wav, "wb") as handle:
                    handle.write(b"first wav payload")
                rows = [{"start": 0.0, "end": 1.2, "source": "silero"}]
                processor._write_vad_timestamps_cache(
                    wav,
                    "silero",
                    {"vad_detection_cache_enabled": True},
                    rows,
                    for_post_stt_align=True,
                )
                cached = processor._load_vad_timestamps_cache(
                    wav,
                    "silero",
                    {"vad_detection_cache_enabled": True},
                    for_post_stt_align=True,
                )

                with open(wav, "wb") as handle:
                    handle.write(b"second wav payload with changed audio")
                replaced = processor._load_vad_timestamps_cache(
                    wav,
                    "silero",
                    {"vad_detection_cache_enabled": True},
                    for_post_stt_align=True,
                )
            finally:
                config.OUTPUT_DIR = old_output_dir

        self.assertEqual(cached, rows)
        self.assertIsNone(replaced)

    def test_detect_vad_timestamps_returns_cached_rows_without_loading_model(self):
        processor = VideoProcessor()
        cached = [{"start": 0.0, "end": 1.0, "source": "silero"}]
        processor._load_vad_timestamps_cache = lambda *args, **kwargs: list(cached)

        result = processor._detect_vad_timestamps(
            "/tmp/does-not-need-to-exist.wav",
            "silero",
            {"vad_detection_cache_enabled": True},
            for_post_stt_align=True,
        )

        self.assertEqual(result, cached)

    def test_stt_vad_uses_media_fingerprint_cache_before_extracting_audio(self):
        old_output_dir = config.OUTPUT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            config.OUTPUT_DIR = tmp
            try:
                media = os.path.join(tmp, "dictation.mp4")
                with open(media, "wb") as handle:
                    handle.write(b"media payload")
                rows = [{"start": 0.0, "end": 1.0, "stt_mode": True}]
                stt_vad._write_stt_vad_cache(media, rows)

                with patch("core.audio.stt_vad._extract_stt_vad_wav") as extract:
                    cached = stt_vad.detect_stt_speech_segments(media)
            finally:
                config.OUTPUT_DIR = old_output_dir

        self.assertEqual(cached, rows)
        extract.assert_not_called()

    def test_stt_vad_releases_silero_model_after_detection(self):
        class _Model:
            def __init__(self):
                self.device = None

            def to(self, device):
                self.device = device

        model = _Model()

        def get_speech_timestamps(*_args, **_kwargs):
            return [{"start": 0, "end": 16000}]

        fake_torch = SimpleNamespace(
            hub=SimpleNamespace(
                load=lambda **_kwargs: (
                    model,
                    (get_speech_timestamps, None, lambda *_args, **_kwargs: [0.0], None, None),
                )
            )
        )

        with patch.dict("sys.modules", {"torch": fake_torch}), \
             patch("core.audio.stt_vad.clear_audio_model_memory_caches") as clear_memory:
            rows = stt_vad._detect_silero_high_sensitivity("/tmp/fake.wav")

        self.assertEqual(rows[0]["start"], 0.0)
        self.assertEqual(rows[0]["end"], 1.0)
        self.assertEqual(model.device, "cpu")
        clear_memory.assert_called_once_with(include_gpu=True)

    def test_lora_query_cache_invalidates_when_media_fingerprint_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            initialize_lora_personalization_store(tmp)
            append_truth_table_rows(
                [
                    TruthTableRow(
                        media_id="demo",
                        media_path="/training/demo.mp4",
                        subtitle_path="/training/demo.srt",
                        segment_id="seg-1",
                        start_sec=0.0,
                        end_sec=1.0,
                        raw_ground_truth_text="차량 리뷰",
                        speech_training_text="차량 리뷰",
                    ).to_record()
                ],
                store_dir=tmp,
            )
            media = os.path.join(tmp, "same.mp4")
            with open(media, "wb") as handle:
                handle.write(b"first media")

            first = retrieve_lora_context("차량 리뷰", media_path=media, store_dir=tmp, limit=4)
            second = retrieve_lora_context("차량 리뷰", media_path=media, store_dir=tmp, limit=4)

            with open(media, "wb") as handle:
                handle.write(b"replacement media with different fingerprint")
            third = retrieve_lora_context("차량 리뷰", media_path=media, store_dir=tmp, limit=4)

        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertFalse(third["cache_hit"])

    def test_waveform_cache_path_and_payload_follow_media_fingerprint(self):
        old_output_dir = config.OUTPUT_DIR
        with tempfile.TemporaryDirectory() as tmp:
            config.OUTPUT_DIR = tmp
            try:
                media = os.path.join(tmp, "same.mp4")
                with open(media, "wb") as handle:
                    handle.write(b"first media")
                first_path = waveform_cache_path(media)
                save_waveform_cache(media, np.array([0.1, 0.5, 0.2], dtype=np.float32), 3.0)
                cached = load_waveform_cache(media)

                with open(media, "wb") as handle:
                    handle.write(b"replacement media")
                second_path = waveform_cache_path(media)
                replaced_cached = load_waveform_cache(media)
            finally:
                config.OUTPUT_DIR = old_output_dir

        self.assertIsNotNone(cached)
        self.assertEqual(cached[1], 3.0)
        self.assertNotEqual(first_path, second_path)
        self.assertIsNone(replaced_cached)


if __name__ == "__main__":
    unittest.main()
