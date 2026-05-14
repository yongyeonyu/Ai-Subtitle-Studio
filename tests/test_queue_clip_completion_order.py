import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.pipeline.pipeline_helpers import PipelineHelpersMixin
from ui.queue.queue_formatting import normalize_queue_status_payload


class _Signal:
    def __init__(self):
        self.emissions = []

    def emit(self, *args):
        self.emissions.append(args)


class _Ui:
    def __init__(self, *, export_video=False):
        self._sig_update_queue_payload = _Signal()
        self._auto_export_subtitle_video = bool(export_video)
        self._is_auto_pipeline = False
        self._current_project_path = ""
        self._editor_widget = SimpleNamespace(
            settings={"subtitle_quality": "high"},
            video_player=SimpleNamespace(current_time=0.0),
        )
        self.done_files = []

    def mark_cloud_file_done(self, filepath):
        self.done_files.append(filepath)


def _queue_statuses(signal: _Signal) -> list[str]:
    statuses = []
    for emission in list(getattr(signal, "emissions", []) or []):
        payload = emission[0] if emission else None
        if isinstance(payload, dict):
            statuses.append(str(normalize_queue_status_payload(payload).get("status") or ""))
    return statuses


class _Backend(PipelineHelpersMixin):
    def __init__(self, ui, media_path):
        self.ui = ui
        self.files_to_process = [media_path]

    def _send_ntfy_notification(self, **_kwargs):
        pass


class _Tracker:
    def mark_completed(self, _filepath):
        pass


class QueueClipCompletionOrderTests(unittest.TestCase):
    def test_queue_clip_always_exports_video_after_srt_and_project_save(self):
        operations = []
        with tempfile.TemporaryDirectory() as tmp:
            media_path = os.path.join(tmp, "clip_a.mp4")
            open(media_path, "wb").close()
            project_path = os.path.join(tmp, "clip_a.ai_project.json")
            ui = _Ui(export_video=False)
            backend = _Backend(ui, media_path)

            with (
                patch("core.engine.subtitle_engine.save_srt", side_effect=lambda *_args, **_kwargs: operations.append("srt")),
                patch("core.project.project_manager.create_project", side_effect=lambda **_kwargs: operations.append("create_project") or project_path),
                patch("core.project.project_manager.save_project", side_effect=lambda **_kwargs: operations.append("project")),
                patch("ui.dialogs.export_dialog._load_es", return_value={"icloud": False}),
                patch("core.renderer.render_subtitle_mov", side_effect=lambda *_args, **_kwargs: operations.append("render") or True),
                patch("core.auto_tracker.AutoTracker", return_value=_Tracker()),
            ):
                ok = backend._save_and_export(media_path, 0, [{"start": 0.0, "end": 1.0, "text": "hello"}], True)

            statuses = _queue_statuses(ui._sig_update_queue_payload)
            self.assertTrue(ok)
            self.assertEqual(operations, ["srt", "create_project", "project", "render"])
            self.assertEqual(statuses[-1], "✅ 완료")
            self.assertLess(statuses.index("💾 SRT 저장 중"), statuses.index("📦 프로젝트 저장 중"))
            self.assertLess(statuses.index("📦 프로젝트 저장 중"), statuses.index("🎥 자막영상출력(mov)"))
            self.assertLess(statuses.index("🎥 자막영상출력(mov)"), statuses.index("✅ 완료"))

    def test_queue_clip_video_export_finishes_before_complete_status(self):
        operations = []
        with tempfile.TemporaryDirectory() as tmp:
            media_path = os.path.join(tmp, "clip_b.mp4")
            open(media_path, "wb").close()
            project_path = os.path.join(tmp, "clip_b.ai_project.json")
            ui = _Ui(export_video=False)
            backend = _Backend(ui, media_path)

            with (
                patch("core.engine.subtitle_engine.save_srt", side_effect=lambda *_args, **_kwargs: operations.append("srt")),
                patch("core.project.project_manager.create_project", side_effect=lambda **_kwargs: operations.append("create_project") or project_path),
                patch("core.project.project_manager.save_project", side_effect=lambda **_kwargs: operations.append("project")),
                patch("ui.dialogs.export_dialog._load_es", return_value={"icloud": False}),
                patch("core.renderer.render_subtitle_mov", side_effect=lambda *_args, **_kwargs: operations.append("render") or True),
                patch("core.auto_tracker.AutoTracker", return_value=_Tracker()),
            ):
                ok = backend._save_and_export(media_path, 0, [{"start": 0.0, "end": 1.0, "text": "hello"}], True)

            statuses = _queue_statuses(ui._sig_update_queue_payload)
            self.assertTrue(ok)
            self.assertEqual(operations, ["srt", "create_project", "project", "render"])
            self.assertLess(statuses.index("🎥 자막영상출력(mov)"), statuses.index("✅ 완료"))
            self.assertEqual(statuses[-1], "✅ 완료")

    def test_queue_clip_does_not_mark_complete_when_video_export_fails(self):
        operations = []
        with tempfile.TemporaryDirectory() as tmp:
            media_path = os.path.join(tmp, "clip_c.mp4")
            open(media_path, "wb").close()
            project_path = os.path.join(tmp, "clip_c.ai_project.json")
            ui = _Ui(export_video=True)
            backend = _Backend(ui, media_path)

            with (
                patch("core.engine.subtitle_engine.save_srt", side_effect=lambda *_args, **_kwargs: operations.append("srt")),
                patch("core.project.project_manager.create_project", side_effect=lambda **_kwargs: operations.append("create_project") or project_path),
                patch("core.project.project_manager.save_project", side_effect=lambda **_kwargs: operations.append("project")),
                patch("ui.dialogs.export_dialog._load_es", return_value={"icloud": False}),
                patch("core.renderer.render_subtitle_mov", side_effect=lambda *_args, **_kwargs: operations.append("render") or False),
            ):
                ok = backend._save_and_export(media_path, 0, [{"start": 0.0, "end": 1.0, "text": "hello"}], True)

            statuses = _queue_statuses(ui._sig_update_queue_payload)
            self.assertFalse(ok)
            self.assertEqual(operations, ["srt", "create_project", "project", "render"])
            self.assertIn("❌ 자막영상출력 실패", statuses)
            self.assertNotIn("✅ 완료", statuses)


if __name__ == "__main__":
    unittest.main()
