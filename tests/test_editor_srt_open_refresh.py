import unittest
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PyQt6.QtWidgets import QApplication

from core.project.project_context import project_segments_to_editor
from ui.editor.editor_lifecycle import EditorLifecycleMixin
from ui.editor.editor_segments_runtime_cache import EditorSegmentsRuntimeCacheMixin
from ui.editor.subtitle_text_edit import SubtitleBlockData, SubtitleTextEdit


class _TextEdit:
    def __init__(self):
        self.margin_updates = 0
        self.timestamp_refreshes = 0

    def update_margins(self):
        self.margin_updates += 1

    def refresh_timestamp_layer(self):
        self.timestamp_refreshes += 1


class _VideoPlayer:
    def __init__(self):
        self.provider = None
        self.display_time = None

    def set_subtitle_provider(self, provider):
        self.provider = provider

    def set_subtitle_display_time(self, sec):
        self.display_time = sec


class _Editor:
    def __init__(self):
        self._cached_segs = [{"start": 9.0, "end": 10.0, "text": "테스트"}]
        self.text_edit = _TextEdit()
        self.video_player = _VideoPlayer()
        self.timeline = SimpleNamespace(canvas=SimpleNamespace(playhead_sec=9.0))
        self.rebuilt_with = None
        self.timestamp_full = None
        self.video_context_refreshed = False

    def _rebuild_subtitle_memory_cache(self, segments=None):
        self.rebuilt_with = list(segments or [])
        return {}

    def _refresh_editor_timestamp_metadata(self, *, full=False):
        self.timestamp_full = full
        return 1

    def _refresh_video_subtitle_context(self):
        self.video_context_refreshed = True

    def _video_subtitle_context_for_player(self):
        return list(self._cached_segs)

    def _global_to_local_sec(self, sec):
        return float(sec)


class _RuntimeCacheProbe(EditorSegmentsRuntimeCacheMixin):
    def __init__(self):
        self.text_edit = SubtitleTextEdit()
        self.settings = {}
        self.video_player = SimpleNamespace(total_time=0.0)
        self.timeline = SimpleNamespace(canvas=SimpleNamespace(segments=[]))
        self._cached_segs = []
        self._cached_line_map = {}
        self._segment_cache_valid = False

    def _frame_time(self, sec):
        return float(sec)

    def _get_current_segments(self, force_rebuild=False):
        return []

    def _clamp_segments_to_clip_duration(self, segments, *, log_changes=True):
        return list(segments or [])


class _Lifecycle(EditorLifecycleMixin):
    pass


class EditorSrtOpenRefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_direct_srt_refresh_restores_timestamp_and_video_context(self):
        editor = _Editor()

        _Lifecycle()._refresh_opened_srt_editor_runtime(editor)

        self.assertEqual(editor.rebuilt_with, editor._cached_segs)
        self.assertTrue(editor.timestamp_full)
        self.assertEqual(editor.text_edit.margin_updates, 1)
        self.assertEqual(editor.text_edit.timestamp_refreshes, 1)
        self.assertTrue(editor.video_context_refreshed)
        self.assertIsNotNone(editor.video_player.provider)
        self.assertEqual(editor.video_player.provider(), editor._cached_segs)
        self.assertEqual(editor.video_player.display_time, 9.0)

    def test_reuse_completion_suppresses_post_generation_tasks(self):
        class _ReuseEditor:
            def __init__(self):
                self.calls = []
                self.redraws = 0

            def _set_process_completed(self, suppress_post_generation_tasks=False):
                self.calls.append(bool(suppress_post_generation_tasks))

            def _redraw_timeline(self):
                self.redraws += 1

        lifecycle = _Lifecycle()
        lifecycle._schedule_editor_fit_to_view = lambda editor, delay_ms=0: None
        editor = _ReuseEditor()

        with mock.patch("ui.editor.editor_lifecycle.QTimer.singleShot", side_effect=lambda _delay, callback: callback()):
            lifecycle._finalize_reuse_completion(editor)

        self.assertEqual(editor.calls, [True])
        self.assertEqual(editor.redraws, 1)

    def test_direct_srt_open_finds_project_asset_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_path = root / "demo.json"
            media_path = root / "demo.mp4"
            srt_path = root / "demo.assets" / "subtitles" / "final.srt"
            media_path.write_bytes(b"video")
            srt_path.parent.mkdir(parents=True)
            srt_path.write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nSRT 수정 텍스트\n\n",
                encoding="utf-8",
            )
            project_path.write_text(
                json.dumps(
                    {
                        "app": "AI Subtitle Studio",
                        "subtitles": {"srt_path": "demo.assets/subtitles/final.srt"},
                        "media": [{"order": 0, "path": str(media_path)}],
                        "editor_state": {
                            "media_files": [str(media_path)],
                            "rendering": {
                                "subtitle_canvas": {
                                    "schema": "subtitle_canvas.vector.v2",
                                    "segments": [
                                        {
                                            "start": 1.0,
                                            "end": 2.0,
                                            "text": "프로젝트 텍스트",
                                            "speaker": "02",
                                            "quality": {"confidence_label": "red"},
                                            "subtitle_stage_confidence": {
                                                "stages": {"stt": {"label": "yellow", "score": 61}},
                                                "stage_order": ["stt"],
                                            },
                                        }
                                    ],
                                }
                            },
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            lifecycle = _Lifecycle()
            found_path, project = lifecycle._find_project_for_srt_open(str(srt_path), str(media_path))

            self.assertEqual(found_path, str(project_path))
            self.assertIsInstance(project, dict)

    def test_direct_srt_metadata_merge_preserves_srt_text_and_restores_project_tags(self):
        lifecycle = _Lifecycle()
        srt_segments = [{"start": 1.0, "end": 2.0, "text": "SRT 수정 텍스트", "is_gap": False}]
        project_segments = project_segments_to_editor(
            {
                "segments": [
                    {
                        "start": 1.0,
                        "end": 2.0,
                        "text": "프로젝트 텍스트",
                        "speaker": "02",
                        "quality": {"confidence_label": "red"},
                        "quality_candidates": [{"candidate_id": "c1", "text": "후보"}],
                        "subtitle_stage_confidence": {
                            "stages": {"stt": {"label": "yellow", "score": 61}},
                            "stage_order": ["stt"],
                        },
                    }
                ]
            }
        )

        merged = lifecycle._merge_srt_segments_with_project_metadata(srt_segments, project_segments)

        self.assertEqual(merged[0]["text"], "SRT 수정 텍스트")
        self.assertEqual(merged[0]["speaker"], "02")
        self.assertEqual(merged[0]["quality"]["confidence_label"], "red")
        self.assertEqual(merged[0]["quality_candidates"][0]["candidate_id"], "c1")
        self.assertEqual(merged[0]["subtitle_stage_confidence"]["stages"]["stt"]["label"], "yellow")
        self.assertEqual(merged[0]["line"], 0)

    def test_linked_project_srt_open_uses_project_restore_helper(self):
        class _DelegatingLifecycle(EditorLifecycleMixin):
            def __init__(self):
                self._current_work_mode = ""
                self._project_boundary_times = []
                self._editor_widget = None
                self.open_calls = []

            def _remove_old_editor(self):
                return None

            def _open_project_segments_in_editor(self, filepath, project, media, segments, **kwargs):
                self.open_calls.append((filepath, project, list(media or []), list(segments or []), dict(kwargs)))
                return True

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            srt_path = root / "demo.assets" / "subtitles" / "final.srt"
            media_path = root / "demo.mp4"
            project_path = root / "demo.aissproj"
            srt_path.parent.mkdir(parents=True)
            srt_path.write_text("1\n00:00:01,000 --> 00:00:02,000\nSRT 수정 텍스트\n\n", encoding="utf-8")
            media_path.write_bytes(b"video")
            project_path.write_text("{}", encoding="utf-8")

            lifecycle = _DelegatingLifecycle()
            linked_project = {
                "media": [{"order": 0, "path": str(media_path)}],
                "editor_state": {"media_files": [str(media_path)]},
            }
            merged_segments = [{"start": 1.0, "end": 2.0, "text": "SRT 수정 텍스트", "speaker": "02"}]

            with mock.patch("ui.editor.editor_lifecycle.detach_project_session"), \
                 mock.patch("ui.editor.editor_lifecycle.attach_project_session"), \
                 mock.patch("core.subtitle_existing.find_media_for_srt", return_value=str(media_path)), \
                 mock.patch("core.subtitle_existing.validate_srt_duration", return_value=(True, "")), \
                 mock.patch("core.srt_parser.parse_srt", return_value=[{"start": 1.0, "end": 2.0, "text": "SRT 수정 텍스트"}]), \
                 mock.patch.object(_DelegatingLifecycle, "_find_project_for_srt_open", return_value=(str(project_path), linked_project)), \
                 mock.patch.object(_DelegatingLifecycle, "_merge_srt_segments_with_project_metadata", return_value=merged_segments), \
                 mock.patch("core.project.project_context.project_segments_to_editor", return_value=[{"start": 1.0, "end": 2.0, "text": "프로젝트"}]):
                lifecycle._open_srt_in_editor(str(srt_path))

        self.assertEqual(len(lifecycle.open_calls), 1)
        filepath, project, media, segments, kwargs = lifecycle.open_calls[0]
        self.assertEqual(filepath, str(project_path))
        self.assertEqual(project, linked_project)
        self.assertEqual(media, [str(media_path)])
        self.assertEqual(segments, merged_segments)
        self.assertEqual(kwargs["source_srt_path"], str(srt_path))
        self.assertTrue(kwargs["direct_srt_edit_mode"])

    def test_linked_project_srt_open_prioritizes_exact_join_sidecar_boundaries(self):
        class _DelegatingLifecycle(EditorLifecycleMixin):
            def __init__(self):
                self._current_work_mode = ""
                self._project_boundary_times = [{"timeline_sec": 99.0, "source": "project"}]
                self._startup_exact_cut_boundary_seed_rows = []
                self._startup_exact_cut_boundary_seed_source = ""
                self._editor_widget = None
                self.open_calls = []

            def _remove_old_editor(self):
                return None

            def _open_project_segments_in_editor(self, filepath, project, media, segments, **kwargs):
                self.open_calls.append(
                    (
                        filepath,
                        project,
                        list(media or []),
                        list(segments or []),
                        dict(kwargs),
                        list(self._project_boundary_times or []),
                    )
                )
                return True

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            srt_path = root / "demo.assets" / "subtitles" / "final.srt"
            media_path = root / "demo.mp4"
            project_path = root / "demo.aissproj"
            sidecar_path = srt_path.with_name("final_edl.json")
            srt_path.parent.mkdir(parents=True)
            srt_path.write_text("1\n00:00:01,000 --> 00:00:02,000\nSRT 수정 텍스트\n\n", encoding="utf-8")
            media_path.write_bytes(b"video")
            project_path.write_text("{}", encoding="utf-8")
            sidecar_path.write_text(
                json.dumps(
                    {
                        "stitched_cut_boundaries": [
                            {
                                "timeline_sec": 4.0,
                                "time": 4.0,
                                "source": "roughcut_concat_join",
                                "detector": "roughcut-edl-join-v1",
                                "verified": True,
                            },
                            {
                                "timeline_sec": 8.0,
                                "time": 8.0,
                                "source": "roughcut_concat_join",
                                "detector": "roughcut-edl-join-v1",
                                "verified": True,
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            lifecycle = _DelegatingLifecycle()
            linked_project = {
                "media": [{"order": 0, "path": str(media_path)}],
                "editor_state": {"media_files": [str(media_path)]},
                "analysis": {"cut_boundaries": [{"timeline_sec": 99.0, "source": "project"}]},
            }
            merged_segments = [{"start": 1.0, "end": 2.0, "text": "SRT 수정 텍스트", "speaker": "02"}]

            with mock.patch("ui.editor.editor_lifecycle.detach_project_session"), \
                 mock.patch("ui.editor.editor_lifecycle.attach_project_session"), \
                 mock.patch("core.subtitle_existing.find_media_for_srt", return_value=str(media_path)), \
                 mock.patch("core.subtitle_existing.validate_srt_duration", return_value=(True, "")), \
                 mock.patch("core.srt_parser.parse_srt", return_value=[{"start": 1.0, "end": 2.0, "text": "SRT 수정 텍스트"}]), \
                 mock.patch.object(_DelegatingLifecycle, "_find_project_for_srt_open", return_value=(str(project_path), linked_project)), \
                 mock.patch.object(_DelegatingLifecycle, "_merge_srt_segments_with_project_metadata", return_value=merged_segments), \
                 mock.patch("core.project.project_context.project_segments_to_editor", return_value=[{"start": 1.0, "end": 2.0, "text": "프로젝트"}]):
                lifecycle._open_srt_in_editor(str(srt_path))

        self.assertEqual(len(lifecycle.open_calls), 1)
        filepath, project, media, segments, kwargs, boundary_rows = lifecycle.open_calls[0]
        self.assertEqual(filepath, str(project_path))
        self.assertEqual(project, linked_project)
        self.assertEqual(media, [str(media_path)])
        self.assertEqual(segments, merged_segments)
        self.assertEqual(kwargs["source_srt_path"], str(srt_path))
        self.assertTrue(kwargs["direct_srt_edit_mode"])
        self.assertEqual([row["timeline_sec"] for row in boundary_rows], [4.0, 8.0])
        self.assertEqual([row["timeline_sec"] for row in lifecycle._startup_exact_cut_boundary_seed_rows], [4.0, 8.0])
        self.assertEqual(Path(lifecycle._startup_exact_cut_boundary_seed_source).name, "final_edl.json")

    def test_unlinked_srt_open_uses_subtitle_only_shared_bootstrap(self):
        class _DelegatingLifecycle(EditorLifecycleMixin):
            def __init__(self):
                self._current_work_mode = ""
                self._project_boundary_times = []
                self._editor_widget = None
                self.subtitle_calls = []

            def _remove_old_editor(self):
                return None

            def _open_project_segments_in_editor(self, *_args, **_kwargs):
                raise AssertionError("unlinked SRT should not restore project metadata")

            def _open_subtitle_segments_in_editor(self, srt_path, media_path, segments):
                self.subtitle_calls.append((srt_path, media_path, list(segments or [])))
                return True

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            srt_path = root / "external.srt"
            media_path = root / "external.mp4"
            srt_path.write_text("1\n00:00:01,000 --> 00:00:02,000\n외부 SRT\n\n", encoding="utf-8")
            media_path.write_bytes(b"video")

            lifecycle = _DelegatingLifecycle()
            parsed_segments = [{"start": 1.0, "end": 2.0, "text": "외부 SRT"}]

            with mock.patch("ui.editor.editor_lifecycle.detach_project_session"), \
                 mock.patch("core.subtitle_existing.find_media_for_srt", return_value=str(media_path)), \
                 mock.patch("core.subtitle_existing.validate_srt_duration", return_value=(True, "")), \
                 mock.patch("core.srt_parser.parse_srt", return_value=parsed_segments), \
                 mock.patch.object(_DelegatingLifecycle, "_find_project_for_srt_open", return_value=("", None)):
                lifecycle._open_srt_in_editor(str(srt_path))

        self.assertEqual(lifecycle.subtitle_calls, [(str(srt_path), str(media_path), parsed_segments)])

    def test_unlinked_srt_open_restores_stitched_boundaries_from_render_plan_sidecar(self):
        class _Signal:
            def connect(self, _callback):
                return None

        class _Timeline:
            def __init__(self):
                self.auto_gap_segments_enabled = False
                self.boundary_times = []
                self.canvas = SimpleNamespace(
                    playhead_sec=0.0,
                    boundary_times=[],
                    segments=[],
                    total_duration=0.0,
                    _segments_content_duration=0.0,
                )
                self.global_canvas = SimpleNamespace(total_duration=0.0, segments=[])
                self.waveform_paths = []

            def set_auto_gap_segments_enabled(self, enabled):
                self.auto_gap_segments_enabled = bool(enabled)

            def load_waveform(self, path, force=False):
                self.waveform_paths.append((str(path), bool(force)))

        class _OpenEditor:
            def __init__(self):
                self.timeline = _Timeline()
                self.text_edit = _TextEdit()
                self.video_player = _VideoPlayer()
                self.sig_next = _Signal()
                self._cached_segs = []
                self.applied_segments = None
                self.applied_kwargs = None
                self.video_context_refreshed = False
                self.timestamp_full = None
                self.scheduled = False

            def apply_loaded_canvas_state(self, segments, **kwargs):
                self.applied_segments = [dict(seg) for seg in list(segments or [])]
                self.applied_kwargs = dict(kwargs)
                self._cached_segs = [dict(seg) for seg in list(segments or [])]
                self.timeline.boundary_times = list(kwargs.get("boundary_times") or [])
                self.timeline.canvas.boundary_times = list(self.timeline.boundary_times)
                return list(self._cached_segs)

            def _schedule_timeline(self):
                self.scheduled = True

            def _rebuild_subtitle_memory_cache(self, segments=None):
                self._cached_segs = [dict(seg) for seg in list(segments if segments is not None else self._cached_segs)]
                return {}

            def _refresh_editor_timestamp_metadata(self, *, full=False):
                self.timestamp_full = bool(full)
                return len(self._cached_segs)

            def _refresh_video_subtitle_context(self):
                self.video_context_refreshed = True

            def _video_subtitle_context_for_player(self):
                return list(self._cached_segs)

            def _global_to_local_sec(self, sec):
                return float(sec)

        class _OpenLifecycle(EditorLifecycleMixin):
            def __init__(self, editor):
                self._current_work_mode = ""
                self._project_boundary_times = [{"timeline_sec": 99.0, "source": "stale"}]
                self._editor_widget = None
                self._next_editor = editor
                self.init_calls = []

            def _remove_old_editor(self):
                return None

            def _init_editor(self, target_file, is_batch=False):
                self.init_calls.append((str(target_file), bool(is_batch)))
                self._editor_widget = self._next_editor

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            srt_path = root / "clip_roughcut.srt"
            media_path = root / "clip.mp4"
            plan_path = root / "clip_roughcut_render_plan.json"
            srt_path.write_text("1\n00:00:01,000 --> 00:00:02,000\n외부 SRT\n\n", encoding="utf-8")
            media_path.write_bytes(b"video")
            plan_path.write_text(
                json.dumps(
                    {
                        "render_plan": {
                            "stitched_cut_boundaries": [
                                {
                                    "timeline_sec": 4.0,
                                    "time": 4.0,
                                    "frame": 120,
                                    "source": "roughcut_concat_join",
                                    "reason": "roughcut_concat_segment_join",
                                    "status": "confirmed",
                                    "verified": True,
                                    "segment_before_id": "chapter_0001",
                                    "segment_after_id": "chapter_0002",
                                    "timeline_before_end": 4.0,
                                    "timeline_after_start": 5.0,
                                }
                            ]
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            editor = _OpenEditor()
            lifecycle = _OpenLifecycle(editor)
            parsed_segments = [{"start": 1.0, "end": 2.0, "text": "외부 SRT"}]

            with mock.patch("ui.editor.editor_lifecycle.QTimer.singleShot", side_effect=lambda _delay, callback: callback()), \
                 mock.patch("ui.editor.editor_project_open_native.QTimer.singleShot", side_effect=lambda _delay, callback: callback()), \
                 mock.patch("ui.editor.editor_lifecycle.detach_project_session"), \
                 mock.patch("core.subtitle_existing.find_media_for_srt", return_value=str(media_path)), \
                 mock.patch("core.subtitle_existing.validate_srt_duration", return_value=(True, "")), \
                 mock.patch("core.srt_parser.parse_srt", return_value=parsed_segments), \
                 mock.patch.object(_OpenLifecycle, "_find_project_for_srt_open", return_value=("", None)):
                lifecycle._open_srt_in_editor(str(srt_path))

        self.assertEqual(lifecycle.init_calls, [(str(media_path), False)])
        self.assertEqual([row["timeline_sec"] for row in lifecycle._project_boundary_times], [4.0])
        self.assertEqual([row["timeline_sec"] for row in lifecycle._startup_exact_cut_boundary_seed_rows], [4.0])
        self.assertEqual(Path(lifecycle._startup_exact_cut_boundary_seed_source).name, "clip_roughcut_render_plan.json")
        self.assertEqual([row["timeline_sec"] for row in editor.applied_kwargs["boundary_times"]], [4.0])
        self.assertEqual(editor.applied_segments, parsed_segments)
        self.assertTrue(editor.timeline.auto_gap_segments_enabled)
        self.assertTrue(editor.video_context_refreshed)
        self.assertTrue(editor.timestamp_full)

    def test_unlinked_srt_open_reuses_current_media_when_srt_has_no_exact_sidecar(self):
        class _DelegatingLifecycle(EditorLifecycleMixin):
            def __init__(self, media_path):
                self._current_work_mode = ""
                self._project_boundary_times = [{"timeline_sec": 99.0, "source": "stale"}]
                self._editor_widget = SimpleNamespace(media_path=str(media_path))
                self.subtitle_calls = []

            def _remove_old_editor(self):
                return None

            def _open_subtitle_segments_in_editor(self, srt_path, media_path, segments):
                self.subtitle_calls.append((srt_path, media_path, list(segments or []), list(self._project_boundary_times or [])))
                return True

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_path = root / "clip.mp4"
            srt_path = root / "clip_done.srt"
            media_path.write_bytes(b"video")
            srt_path.write_text("1\n00:00:01,000 --> 00:00:02,000\n외부 SRT\n\n", encoding="utf-8")
            parsed_segments = [{"start": 1.0, "end": 2.0, "text": "외부 SRT"}]
            lifecycle = _DelegatingLifecycle(media_path)

            with mock.patch("ui.editor.editor_lifecycle.detach_project_session"), \
                 mock.patch("core.subtitle_existing.find_media_for_srt", return_value=""), \
                 mock.patch("core.subtitle_existing.validate_srt_duration", return_value=(True, "")) as validate, \
                 mock.patch("core.srt_parser.parse_srt", return_value=parsed_segments), \
                 mock.patch.object(_DelegatingLifecycle, "_find_project_for_srt_open", return_value=("", None)):
                lifecycle._open_srt_in_editor(str(srt_path))

        validate.assert_called_once_with(str(srt_path), str(media_path))
        self.assertEqual(lifecycle._project_boundary_times, [])
        self.assertEqual(getattr(lifecycle, "_startup_exact_cut_boundary_seed_rows", []), [])
        self.assertEqual(getattr(lifecycle, "_startup_exact_cut_boundary_seed_source", ""), "")
        self.assertEqual(lifecycle.subtitle_calls, [(str(srt_path), str(media_path), parsed_segments, [])])

    def test_timestamp_area_uses_cached_srt_segments_when_block_metadata_is_missing(self):
        text_edit = SubtitleTextEdit()
        try:
            text_edit.setPlainText("첫 줄")
            block = text_edit.document().findBlockByNumber(0)
            block.setUserData(None)
            text_edit._timestamp_block_meta_snapshot = {}

            parent = SimpleNamespace()
            parent._cached_line_map = {
                0: {"line": 0, "start": 1.25, "end": 2.5, "text": "첫 줄", "speaker": "01"}
            }
            parent._refresh_cached_line_map = lambda: parent._cached_line_map
            parent._segment_matches_block_text = lambda seg, text: str(seg.get("text")) == str(text)
            text_edit._parent_widget = parent

            data = text_edit.timestampArea._block_user_data(block)

            self.assertAlmostEqual(data.start_sec, 1.25)
            self.assertEqual(data.spk_id, "01")
            self.assertFalse(data.is_gap)
        finally:
            text_edit.close()

    def test_timestamp_area_uses_timeline_segments_when_cached_metadata_is_missing(self):
        text_edit = SubtitleTextEdit()
        try:
            text_edit.setPlainText("첫 줄")
            block = text_edit.document().findBlockByNumber(0)
            block.setUserData(None)
            text_edit._timestamp_block_meta_snapshot = {}

            parent = SimpleNamespace()
            parent._cached_line_map = {}
            parent._refresh_cached_line_map = lambda: {}
            parent._timestamp_restore_line_map_from_timeline = lambda: {
                0: {"line": 0, "start": 4.5, "end": 6.0, "text": "첫 줄", "speaker": "02"}
            }
            parent._segment_matches_block_text = lambda seg, text: str(seg.get("text")) == str(text)
            text_edit._parent_widget = parent

            data = text_edit.timestampArea._block_user_data(block)

            self.assertAlmostEqual(data.start_sec, 4.5)
            self.assertEqual(data.spk_id, "02")
        finally:
            text_edit.close()

    def test_runtime_timestamp_repair_uses_timeline_segments_when_cache_is_empty(self):
        editor = _RuntimeCacheProbe()
        try:
            editor.text_edit.setPlainText("첫 줄\n둘째 줄")
            block = editor.text_edit.document().begin()
            while block.isValid():
                block.setUserData(None)
                block = block.next()
            editor.timeline.canvas.segments = [
                {"line": 0, "start": 1.25, "end": 2.5, "text": "첫 줄", "speaker": "01"},
                {"line": 1, "start": 3.75, "end": 5.0, "text": "둘째 줄", "speaker": "02"},
            ]

            repaired = editor._restore_all_block_user_data()

            self.assertEqual(repaired, 2)
            first = editor.text_edit.document().findBlockByNumber(0).userData()
            second = editor.text_edit.document().findBlockByNumber(1).userData()
            self.assertIsInstance(first, SubtitleBlockData)
            self.assertIsInstance(second, SubtitleBlockData)
            self.assertAlmostEqual(first.start_sec, 1.25)
            self.assertAlmostEqual(second.start_sec, 3.75)
        finally:
            editor.text_edit.close()

    def test_timestamp_area_prefers_canonical_snapshot_when_runtime_snapshot_drifted(self):
        text_edit = SubtitleTextEdit()
        try:
            text_edit.setPlainText("첫 줄")
            block = text_edit.document().findBlockByNumber(0)
            block.setUserData(None)
            text_edit._canonical_timestamp_block_meta_snapshot = {
                0: {"spk_id": "00", "start_sec": 1.25, "end_sec": 2.5, "is_gap": False}
            }
            text_edit._canonical_timestamp_block_text_snapshot = {0: "첫 줄"}
            text_edit._timestamp_block_meta_snapshot = {
                0: {"spk_id": "00", "start_sec": 8.75, "end_sec": 9.5, "is_gap": False}
            }

            data = text_edit.timestampArea._block_user_data(block)

            self.assertAlmostEqual(data.start_sec, 1.25)
            self.assertFalse(data.is_gap)
        finally:
            text_edit.close()

    def test_timestamp_layer_refresh_repairs_visible_metadata_before_paint(self):
        text_edit = SubtitleTextEdit()
        try:
            text_edit.setPlainText("첫 줄")
            block = text_edit.document().findBlockByNumber(0)
            block.setUserData(None)
            calls = []

            def _repair_visible():
                calls.append(True)
                block.setUserData(SubtitleBlockData("00", 7.1, False, end_sec=8.2))
                return 1

            text_edit._parent_widget = SimpleNamespace(_restore_visible_block_user_data=_repair_visible)

            self.assertTrue(text_edit.refresh_timestamp_layer())

            self.assertEqual(len(calls), 1)
            self.assertIsInstance(block.userData(), SubtitleBlockData)
            self.assertAlmostEqual(block.userData().start_sec, 7.1)
        finally:
            text_edit.close()

    def test_timestamp_layer_refresh_reenables_timestamp_area_updates(self):
        text_edit = SubtitleTextEdit()
        try:
            text_edit.timestampArea.setUpdatesEnabled(False)

            self.assertTrue(text_edit.refresh_timestamp_layer())

            self.assertTrue(text_edit.timestampArea.updatesEnabled())
        finally:
            text_edit.close()

    def test_margin_refresh_repairs_visible_srt_block_metadata_before_paint(self):
        text_edit = SubtitleTextEdit()
        try:
            text_edit.setPlainText("첫 줄")
            block = text_edit.document().findBlockByNumber(0)
            block.setUserData(None)
            calls = []

            def _repair_visible():
                calls.append(True)
                block.setUserData(SubtitleBlockData("00", 3.4, False, end_sec=4.2))
                return 1

            text_edit._parent_widget = SimpleNamespace(_restore_visible_block_user_data=_repair_visible)

            text_edit.update_margins()

            self.assertEqual(len(calls), 1)
            self.assertIsInstance(block.userData(), SubtitleBlockData)
            self.assertAlmostEqual(block.userData().start_sec, 3.4)
            self.assertGreaterEqual(text_edit.viewportMargins().left(), 120)
        finally:
            text_edit.close()


if __name__ == "__main__":
    unittest.main()
