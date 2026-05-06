import os
import tempfile
import unittest

import numpy as np

from core.audio.media_processor import VideoProcessor
from core.pipeline.cut_boundary_helpers import PipelineCutBoundaryMixin
from core.personalization.lora_models import TruthTableRow
from core.personalization.lora_storage import append_truth_table_rows, initialize_lora_personalization_store
from core.personalization.lora_vector_retriever import retrieve_lora_context
from core.runtime import config
from ui.timeline.timeline_waveform import load_waveform_cache, save_waveform_cache, waveform_cache_path


class _CutCacheOwner(PipelineCutBoundaryMixin):
    pass


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
