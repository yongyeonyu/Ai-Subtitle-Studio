import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from core.pipeline.background_prefetch import (
    BACKGROUND_PREFETCH_SCHEMA,
    BackgroundPrefetchManager,
    build_background_prefetch_plan,
)
from ui.editor.editor_timeline_video import EditorTimelineVideoMixin


class _PrefetchEditor(EditorTimelineVideoMixin):
    pass


class BackgroundPrefetchTests(unittest.TestCase):
    def test_plan_selects_nearby_segments_and_limits_work(self):
        plan = build_background_prefetch_plan(
            media_path="/tmp/video.mp4",
            current_sec=30.0,
            segments=[
                {"start": 0.0, "end": 1.0, "text": "멀리"},
                {"start": 28.0, "end": 29.0, "text": "근처1"},
                {"start": 35.0, "end": 36.0, "text": "근처2"},
                {"start": 150.0, "end": 151.0, "text": "멀리2"},
            ],
            settings={"background_prefetch_before_sec": 5.0, "background_prefetch_after_sec": 10.0, "background_prefetch_segment_limit": 2},
        )

        self.assertEqual(plan["schema"], BACKGROUND_PREFETCH_SCHEMA)
        self.assertEqual(plan["segment_count"], 2)
        self.assertEqual([row["text"] for row in plan["segments"]], ["근처1", "근처2"])
        self.assertTrue(plan["waveform"]["requested"])

    def test_manager_prefetches_candidate_lattice_without_lora(self):
        manager = BackgroundPrefetchManager()
        result = manager.request(
            media_path="",
            current_sec=1.0,
            segments=[
                {
                    "start": 0.0,
                    "end": 2.0,
                    "text": "현재",
                    "stt_candidates": [{"source": "STT1", "text": "현재"}, {"source": "STT2", "text": "현제"}],
                }
            ],
            settings={
                "background_prefetch_lora_enabled": False,
                "background_prefetch_candidates_enabled": True,
                "background_prefetch_min_interval_sec": 0.0,
            },
        )
        thread = manager._thread
        if thread is not None:
            thread.join(timeout=2.0)

        self.assertTrue(result["queued"])
        self.assertEqual(manager.last_result["candidate_prefetch_count"], 1)
        self.assertEqual(manager.last_result["lora_prefetch_count"], 0)

    def test_clear_ignores_late_prefetch_result(self):
        manager = BackgroundPrefetchManager()
        plan = build_background_prefetch_plan(
            media_path="",
            current_sec=1.0,
            segments=[{"start": 0.0, "end": 2.0, "text": "늦은 결과"}],
            settings={},
        )

        manager.clear()
        manager._run_prefetch(0, plan, {"background_prefetch_lora_enabled": False, "background_prefetch_candidates_enabled": False})

        self.assertEqual(manager.last_result, {})

    def test_editor_background_prefetch_uses_cached_segments_without_document_scan(self):
        editor = _PrefetchEditor()
        editor.settings = {
            "background_prefetch_enabled": True,
            "background_prefetch_lora_enabled": False,
            "background_prefetch_candidates_enabled": False,
            "background_prefetch_min_interval_sec": 0.0,
        }
        editor.media_path = ""
        editor.video_player = SimpleNamespace(path="")
        editor._cached_segs = [{"start": 9.0, "end": 11.0, "text": "캐시"}]
        editor._get_current_segments = Mock(side_effect=AssertionError("document scan should not run"))

        editor._schedule_background_prefetch(10.0)
        manager = editor._background_prefetch_manager
        thread = manager._thread
        if thread is not None:
            thread.join(timeout=2.0)

        editor._get_current_segments.assert_not_called()
        self.assertEqual(editor._last_background_prefetch_request["segment_count"], 1)

    def test_editor_background_prefetch_throttles_before_copying_segments(self):
        class ExplodingSegments:
            def __iter__(self):
                raise AssertionError("segments should not be copied while prefetch is throttled")

        editor = _PrefetchEditor()
        editor.settings = {
            "background_prefetch_enabled": True,
            "background_prefetch_lora_enabled": False,
            "background_prefetch_candidates_enabled": False,
            "background_prefetch_bucket_sec": 6.0,
            "background_prefetch_min_interval_sec": 10.0,
        }
        editor.media_path = "/tmp/video.mp4"
        manager = Mock()
        manager.request.return_value = {"queued": True, "segment_count": 1}
        editor._background_prefetch_manager = manager
        editor._cached_segs = [{"start": 9.0, "end": 11.0, "text": "캐시"}]

        editor._schedule_background_prefetch(10.0)
        editor._cached_segs = ExplodingSegments()
        editor._schedule_background_prefetch(10.2)

        manager.request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
