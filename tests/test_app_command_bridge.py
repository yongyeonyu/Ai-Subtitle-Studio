import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.runtime.logger import get_logger
import ui.main.app_command_bridge as app_bridge
from ui.main.app_command_bridge import execute_app_command


class _DummyEditor:
    def __init__(self, state: str = "ST_IDLE"):
        self.media_path = "/tmp/media.mp4"
        self.sm = SimpleNamespace(state=state)
        self.start_clicks = 0
        self.save_calls = 0
        self.roughcut_starts = 0
        self._on_start_callback = None
        self._playhead_sec = 0.0
        self._shadow_playhead_sec = None
        self._selected_line = 0
        self._inline_edit_active = False
        self._split_pending_sec = None
        self._inline_text = ""
        self._inline_cursor = None
        self._timeline_pps = 12.0
        self._playback_center_lock = False
        self._playing = False
        self._segments = [
            {"line": 0, "start": 0.0, "end": 1.0, "text": "첫 줄", "is_gap": False},
            {"line": 1, "start": 1.0, "end": 2.0, "text": "둘째 줄", "is_gap": False},
        ]

    def _on_start_clicked(self):
        self.start_clicks += 1
        callback = getattr(self, "_on_start_callback", None)
        if callable(callback):
            callback()

    def _on_save(self, skip_auto_next=True):
        self.save_calls += 1
        return True

    def _schedule_post_generation_roughcut_draft(self, force: bool = False):
        self.roughcut_starts += 1
        self.roughcut_force = bool(force)

    def _segment_index(self, *, line: int | None = None, at_playhead: bool = False):
        if line is not None:
            for idx, seg in enumerate(self._segments):
                if int(seg.get("line", -1)) == int(line):
                    return idx
            return None
        if at_playhead:
            for idx, seg in enumerate(self._segments):
                if float(seg["start"]) <= float(self._playhead_sec) <= float(seg["end"]):
                    return idx
        return self._selected_line if 0 <= self._selected_line < len(self._segments) else None

    def automation_editor_state_snapshot(self):
        idx = self._segment_index()
        active = dict(self._segments[idx]) if idx is not None else {}
        prev_seg = dict(self._segments[idx - 1]) if idx is not None and idx > 0 else {}
        next_seg = dict(self._segments[idx + 1]) if idx is not None and (idx + 1) < len(self._segments) else {}
        left_pair = {}
        right_pair = {}
        if idx is not None and idx > 0:
            left = self._segments[idx - 1]
            right = self._segments[idx]
            if abs(float(left["end"]) - float(right["start"])) < 0.001:
                left_pair = {"side": "left", "boundary_sec": float(left["end"]), "left": dict(left), "right": dict(right)}
        if idx is not None and (idx + 1) < len(self._segments):
            left = self._segments[idx]
            right = self._segments[idx + 1]
            if abs(float(left["end"]) - float(right["start"])) < 0.001:
                right_pair = {"side": "right", "boundary_sec": float(left["end"]), "left": dict(left), "right": dict(right)}
        return {
            "playhead_sec": float(self._playhead_sec),
            "shadow_playhead_sec": self._shadow_playhead_sec,
            "shadow_playhead_active": self._shadow_playhead_sec is not None,
            "active_seg_line": active.get("line"),
            "active_seg_start": active.get("start"),
            "segment_count": len(self._segments),
            "gap_count": 0,
            "active_segment": active,
            "previous_segment": prev_seg,
            "next_segment": next_seg,
            "diamond_left": left_pair,
            "diamond_right": right_pair,
            "smart_split_ready": bool(active and float(active["start"]) + 0.05 < float(self._playhead_sec) < float(active["end"]) - 0.05),
            "inline_edit_active": bool(self._inline_edit_active),
            "inline_edit_mode": "smart_split" if self._split_pending_sec is not None else ("plain" if self._inline_edit_active else ""),
            "inline_edit_text": self._inline_text,
            "inline_edit_text_length": len(self._inline_text),
            "inline_edit_cursor": self._inline_cursor,
            "split_pending_sec": self._split_pending_sec,
            "timeline_pps": self._timeline_pps,
            "timeline_scroll_x": 0.0,
            "timeline_fit_locked": False,
            "playback_center_lock": self._playback_center_lock,
        }

    def automation_set_playhead(self, sec: float, *, center: bool = False, sync_video: bool = True):
        self._playhead_sec = float(sec)
        return {
            "playhead_sec": float(sec),
            "center": bool(center),
            "sync_video": bool(sync_video),
            "editor_runtime": self.automation_editor_state_snapshot(),
        }

    def automation_pin_shadow_playhead(self, sec: float | None = None):
        self._shadow_playhead_sec = float(self._playhead_sec if sec is None else sec)
        return {
            "changed": True,
            "shadow_playhead_sec": float(self._shadow_playhead_sec),
            "editor_runtime": self.automation_editor_state_snapshot(),
        }

    def automation_clear_shadow_playhead(self):
        changed = self._shadow_playhead_sec is not None
        self._shadow_playhead_sec = None
        return {
            "changed": changed,
            "editor_runtime": self.automation_editor_state_snapshot(),
        }

    def automation_zoom_max(self):
        self._timeline_pps = 500.0
        return {
            "timeline_pps": self._timeline_pps,
            "editor_runtime": self.automation_editor_state_snapshot(),
        }

    def automation_set_playback_state(self, action: str):
        normalized = str(action or "toggle")
        if normalized == "toggle":
            self._playing = not self._playing
        elif normalized == "play":
            self._playing = True
            self._playback_center_lock = True
        elif normalized == "pause":
            self._playing = False
            self._playback_center_lock = False
        else:
            raise ValueError("invalid_playback_action")
        return {
            "action": normalized,
            "editor_runtime": self.automation_editor_state_snapshot(),
        }

    def automation_select_segment(
        self,
        *,
        line: int | None = None,
        start_sec: float | None = None,
        at_playhead: bool = False,
        center: bool = False,
        sync_playhead: bool = False,
    ):
        idx = None
        if line is not None:
            idx = self._segment_index(line=int(line))
        elif start_sec is not None:
            for raw_idx, seg in enumerate(self._segments):
                if abs(float(seg["start"]) - float(start_sec)) < 0.001:
                    idx = raw_idx
                    break
        elif at_playhead:
            idx = self._segment_index(at_playhead=True)
        if idx is None:
            raise ValueError("segment_not_found")
        self._selected_line = idx
        if sync_playhead:
            self._playhead_sec = float(self._segments[idx]["start"])
        return {
            "selected_line": int(self._segments[idx]["line"]),
            "selected_start": float(self._segments[idx]["start"]),
            "center": bool(center),
            "editor_runtime": self.automation_editor_state_snapshot(),
        }

    def automation_move_segment_boundary_to_playhead(self, edge: str):
        idx = self._segment_index()
        if idx is None:
            raise ValueError("active_segment_missing")
        seg = self._segments[idx]
        if edge == "left":
            seg["start"] = float(self._playhead_sec)
        else:
            seg["end"] = float(self._playhead_sec)
        return {
            "edge": str(edge),
            "line": int(seg["line"]),
            "boundary_sec": float(self._playhead_sec),
            "editor_runtime": self.automation_editor_state_snapshot(),
        }

    def automation_begin_smart_split_at_playhead(self, *, line: int | None = None, start_sec: float | None = None, at_playhead: bool = False):
        selected = self.automation_select_segment(line=line, start_sec=start_sec, at_playhead=at_playhead)
        idx = self._segment_index()
        seg = self._segments[idx]
        if not float(seg["start"]) + 0.05 < float(self._playhead_sec) < float(seg["end"]) - 0.05:
            raise ValueError("smart_split_unavailable")
        self._inline_edit_active = True
        self._split_pending_sec = float(self._playhead_sec)
        self._inline_text = str(seg["text"])
        self._inline_cursor = len(self._inline_text)
        return {
            "line": int(seg["line"]),
            "start": float(seg["start"]),
            "split_sec": float(self._split_pending_sec),
            "selected": selected,
            "editor_runtime": self.automation_editor_state_snapshot(),
        }

    def automation_set_inline_edit_cursor(self, position: int):
        if not self._inline_edit_active:
            raise ValueError("inline_edit_inactive")
        target = int(position)
        if target < 0:
            target = len(self._inline_text) + target
        self._inline_cursor = max(0, min(target, len(self._inline_text)))
        return {
            "cursor": int(self._inline_cursor),
            "text_length": len(self._inline_text),
            "editor_runtime": self.automation_editor_state_snapshot(),
        }

    def automation_commit_inline_edit(self):
        if not self._inline_edit_active:
            raise ValueError("inline_edit_inactive")
        if self._split_pending_sec is not None:
            result = self.automation_smart_split_at_playhead(cursor=self._inline_cursor)
            self._inline_edit_active = False
            self._split_pending_sec = None
            self._inline_text = ""
            self._inline_cursor = None
            return result
        self._inline_edit_active = False
        self._inline_text = ""
        self._inline_cursor = None
        return {"editor_runtime": self.automation_editor_state_snapshot()}

    def automation_move_diamond_to_playhead(self, *, side: str = "closest"):
        idx = self._segment_index()
        if idx is None:
            raise ValueError("active_segment_missing")
        if side == "left":
            if idx == 0:
                raise ValueError("diamond_pair_missing")
            left_idx, right_idx = idx - 1, idx
        else:
            if idx + 1 >= len(self._segments):
                raise ValueError("diamond_pair_missing")
            left_idx, right_idx = idx, idx + 1
        self._segments[left_idx]["end"] = float(self._playhead_sec)
        self._segments[right_idx]["start"] = float(self._playhead_sec)
        return {
            "side": str(side),
            "boundary_sec": float(self._playhead_sec),
            "left_line": int(self._segments[left_idx]["line"]),
            "right_line": int(self._segments[right_idx]["line"]),
            "editor_runtime": self.automation_editor_state_snapshot(),
        }

    def automation_merge_diamond(self, *, side: str = "closest"):
        idx = self._segment_index()
        if idx is None or idx + 1 >= len(self._segments):
            raise ValueError("diamond_pair_missing")
        self._segments[idx]["text"] += " " + self._segments[idx + 1]["text"]
        self._segments[idx]["end"] = float(self._segments[idx + 1]["end"])
        self._segments.pop(idx + 1)
        return {
            "side": str(side),
            "left_line": int(self._segments[idx]["line"]),
            "editor_runtime": self.automation_editor_state_snapshot(),
        }

    def automation_smart_split_at_playhead(self, cursor: int | None = None):
        idx = self._segment_index()
        if idx is None:
            raise ValueError("active_segment_missing")
        seg = self._segments[idx]
        if not float(seg["start"]) + 0.05 < float(self._playhead_sec) < float(seg["end"]) - 0.05:
            raise ValueError("smart_split_unavailable")
        full_text = str(seg["text"] or "")
        split_cursor = len(full_text) if cursor is None else max(0, min(int(cursor), len(full_text)))
        left_text = full_text[:split_cursor].rstrip() or full_text
        right_text = full_text[split_cursor:].lstrip() or "새 자막"
        new_line = max(int(item["line"]) for item in self._segments) + 1
        right = {
            "line": new_line,
            "start": float(self._playhead_sec),
            "end": float(seg["end"]),
            "text": right_text,
            "is_gap": False,
        }
        seg["text"] = left_text
        seg["end"] = float(self._playhead_sec)
        self._segments.insert(idx + 1, right)
        self._selected_line = idx + 1
        return {
            "line": int(seg["line"]),
            "split_sec": float(self._playhead_sec),
            "editor_runtime": self.automation_editor_state_snapshot(),
        }


class _DummyOwner:
    def __init__(self):
        self.home_calls = 0
        self.queue_calls = []
        self.opened_project = ""
        self.saved_project = 0
        self.guided_runs = []
        self.guided_snapshots = []
        self.async_snapshot_requests = []
        self._last_async_snapshot_result = {}
        self._pending_async_snapshots = []
        self._current_project_path = ""
        self._current_work_mode = "editor"
        self._auto_processing_active = False
        self.backend_start_calls = []
        self.multiclip_start_calls = []
        self.applied_settings = []
        self.settings = {}
        self.dictionary_dialog_opened = 0
        self._correction_dictionary_dialog = None
        self.backend = SimpleNamespace(
            _active=False,
            start_pipeline=self._start_pipeline,
            start_multiclip_pipeline=self._start_multiclip_pipeline,
            _force_no_reuse_once=False,
            _force_reuse_existing_multiclip_subtitles_once=False,
        )
        self._editor_widget = _DummyEditor()
        self.last_open_args = None

    def show_home(self, allow_home_idle_learning: bool = False):
        self.home_calls += 1

    def _open_project_file(self, path: str) -> bool:
        self.opened_project = path
        return True

    def _start_queue_mode(self, files, folder=None, source="queue"):
        self.queue_calls.append((list(files), folder, source))

    def _save_current_project(self, segments=None):
        self.saved_project += 1

    def open_editor_for_file_and_wait(self, target_file, *_args):
        self.last_open_args = (target_file, *_args)
        if len(_args) >= 2:
            self._editor_widget._on_start_callback = _args[1]
        self._editor_widget.media_path = str(target_file)
        return True

    def _start_pipeline(self, files, folder=None, is_icloud=False, is_auto_start=False):
        self.backend_start_calls.append(
            {
                "files": list(files or []),
                "folder": folder,
                "is_icloud": bool(is_icloud),
                "is_auto_start": bool(is_auto_start),
            }
        )

    def _start_multiclip_pipeline(self, files, folder=None):
        normalized_files = list(files or [])
        self.multiclip_start_calls.append({"files": normalized_files, "folder": folder})
        if normalized_files:
            self._editor_widget.media_path = str(normalized_files[0])

    def _apply_ai_settings(self, settings: dict):
        self.applied_settings.append(dict(settings))
        self.settings = dict(settings)
        self._editor_widget.settings = dict(settings)

    def _automation_begin_guided_subtitle_run(self, media_path: str, snapshot_dir: str = ""):
        self.guided_runs.append((media_path, snapshot_dir))
        return {"snapshot_dir": snapshot_dir or "/tmp/guided"}

    def _automation_capture_guided_snapshot(self, label: str, *, stage_text: str = "", force: bool = False):
        snapshot = {
            "label": label,
            "stage_text": stage_text,
            "path": f"/tmp/{label}.png",
            "sequence": len(self.guided_snapshots) + 1,
            "force": force,
        }
        self.guided_snapshots.append(snapshot)
        return snapshot

    def isMinimized(self):
        return False

    def show(self):
        return None

    def raise_(self):
        return None

    def activateWindow(self):
        return None

    def grab(self):
        return _DummyPixmap()

    def _automation_request_async_snapshot_capture(self, snapshot_path: str):
        item = {"path": snapshot_path, "requested_at": 123.0}
        self.async_snapshot_requests.append(item)
        self._pending_async_snapshots.append(item)
        return item

    def _automation_guided_snapshot_state_payload(self):
        return {
            "pending_async_snapshot_count": len(self._pending_async_snapshots),
            "pending_async_snapshots": list(self._pending_async_snapshots),
            "last_async_snapshot": dict(self._last_async_snapshot_result),
        }

    def _show_main_correction_dictionary_nonmodal(self):
        self.dictionary_dialog_opened += 1
        self._correction_dictionary_dialog = _DummyVisibleDialog()
        return self._correction_dictionary_dialog


class _DummyPixmap:
    def __init__(self, *, save_ok: bool = True, width: int = 640, height: int = 360):
        self._save_ok = save_ok
        self._width = width
        self._height = height

    def isNull(self):
        return False

    def save(self, path: str, _fmt: str):
        if not self._save_ok:
            return False
        Path(path).write_bytes(b"png")
        return True

    def width(self):
        return self._width

    def height(self):
        return self._height


class _DummyVisibleDialog:
    def __init__(self, *, visible: bool = True, save_ok: bool = True):
        self._visible = bool(visible)
        self._pixmap = _DummyPixmap(save_ok=save_ok, width=1960, height=1280)

    def isVisible(self):
        return self._visible

    def grab(self):
        return self._pixmap


class AppCommandBridgeTests(unittest.TestCase):
    def setUp(self):
        clearer = getattr(get_logger(), "clear_recent_lines", None)
        if callable(clearer):
            clearer()
        app_bridge._clear_status_snapshot_cache()

    def test_open_project_command_uses_path_based_helper(self):
        owner = _DummyOwner()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo.json"
            path.write_text("{}", encoding="utf-8")

            result = execute_app_command(owner, {"command": "open-project", "path": str(path)})

        self.assertTrue(result["ok"])
        self.assertEqual(owner.opened_project, str(path))

    def test_queue_folder_command_orders_media_and_starts_queue(self):
        owner = _DummyOwner()
        with patch("ui.main.app_command_bridge.ordered_media_files", return_value=["/tmp/a.mp4", "/tmp/b.wav"]):
            with patch("os.path.isdir", return_value=True):
                result = execute_app_command(owner, {"command": "queue-folder", "path": "/tmp/folder"})

        self.assertTrue(result["ok"])
        self.assertEqual(owner.queue_calls[0], (["/tmp/a.mp4", "/tmp/b.wav"], "/tmp/folder", "automation"))

    def test_save_project_command_falls_back_to_editor_save_without_project(self):
        owner = _DummyOwner()

        result = execute_app_command(owner, {"command": "save-project"})

        self.assertTrue(result["ok"])
        self.assertEqual(owner._editor_widget.save_calls, 1)
        self.assertEqual(owner.saved_project, 0)

    def test_start_current_pipeline_rejects_duplicate_processing_toggle(self):
        owner = _DummyOwner()
        owner._editor_widget = _DummyEditor(state="ST_PROC")

        result = execute_app_command(owner, {"command": "start-current-pipeline"})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "already_processing")
        self.assertEqual(owner._editor_widget.start_clicks, 0)

    def test_start_current_roughcut_triggers_post_generation_followup(self):
        owner = _DummyOwner()

        result = execute_app_command(owner, {"command": "start-current-roughcut"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "roughcut_started")
        self.assertEqual(owner._editor_widget.roughcut_starts, 1)
        self.assertTrue(owner._editor_widget.roughcut_force)

    def test_open_media_wires_real_pipeline_start_callback(self):
        owner = _DummyOwner()
        with tempfile.TemporaryDirectory() as tmp:
            media_path = Path(tmp) / "demo.mp4"
            media_path.write_bytes(b"video")

            result = execute_app_command(owner, {"command": "open-media", "path": str(media_path)})

        self.assertTrue(result["ok"])
        self.assertEqual(owner.backend_start_calls, [])
        owner._editor_widget._on_start_clicked()
        self.assertEqual(owner.backend_start_calls, [{"files": [str(media_path)], "folder": None, "is_icloud": False, "is_auto_start": True}])

    def test_start_multiclip_command_auto_starts_pipeline_with_mode_override(self):
        owner = _DummyOwner()
        with tempfile.TemporaryDirectory() as tmp:
            files = []
            for name in ("a.mp4", "b.mp4", "c.mp4"):
                path = Path(tmp) / name
                path.write_bytes(b"video")
                files.append(str(path))

            with patch("ui.main.app_command_bridge.load_settings", return_value={"simple_operation_mode": "high"}):
                result = execute_app_command(
                    owner,
                    {
                        "command": "start-multiclip",
                        "paths": files,
                        "options": {"mode": "fast", "reuse_existing": "ask"},
                    },
                )

        self.assertTrue(result["ok"])
        self.assertEqual(owner.multiclip_start_calls, [{"files": files, "folder": tmp}])
        self.assertEqual(owner._editor_widget.start_clicks, 1)
        self.assertEqual(result["message"], "multiclip_started")
        self.assertEqual(result["data"]["mode"], "fast")
        self.assertEqual(result["data"]["stt_quality_preset"], "fast")
        self.assertEqual(owner.applied_settings[-1]["simple_operation_mode"], "fast")

    def test_start_multiclip_command_requires_explicit_reuse_policy_when_srts_exist(self):
        owner = _DummyOwner()
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "a.mp4"
            second = Path(tmp) / "b.mp4"
            first.write_bytes(b"video")
            second.write_bytes(b"video")
            (Path(tmp) / "a.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\ntext\n", encoding="utf-8")

            result = execute_app_command(
                owner,
                {
                    "command": "start-multiclip",
                    "paths": [str(first), str(second)],
                    "options": {"reuse_existing": "ask"},
                },
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "existing_subtitles_confirmation_required")
        self.assertEqual(owner.multiclip_start_calls, [])

    def test_start_multiclip_command_can_force_no_reuse_for_existing_srts(self):
        owner = _DummyOwner()
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "a.mp4"
            second = Path(tmp) / "b.mp4"
            first.write_bytes(b"video")
            second.write_bytes(b"video")
            (Path(tmp) / "a.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\ntext\n", encoding="utf-8")

            result = execute_app_command(
                owner,
                {
                    "command": "start-multiclip",
                    "paths": [str(first), str(second)],
                    "options": {"reuse_existing": "no"},
                },
            )

        self.assertTrue(result["ok"])
        self.assertTrue(owner.backend._force_no_reuse_once)
        self.assertFalse(owner.backend._force_reuse_existing_multiclip_subtitles_once)
        self.assertEqual(owner.multiclip_start_calls[0]["files"], [str(first), str(second)])

    def test_status_command_reports_current_runtime_snapshot(self):
        owner = _DummyOwner()
        owner._current_project_path = "/tmp/project.json"
        owner._runtime_resource_snapshot = {"rss_gb": 1.25, "pressure_stage": "normal"}
        owner.backend._active = True
        get_logger().log("status log line")
        get_logger().log("🎯 자막 생성 중")

        result = execute_app_command(owner, {"command": "status"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["current_project_path"], "/tmp/project.json")
        self.assertTrue(result["data"]["backend_active"])
        self.assertTrue(result["data"]["editor_open"])
        self.assertEqual(result["data"]["editor_runtime"]["segment_count"], 2)
        self.assertEqual(result["data"]["runtime_resource"]["rss_gb"], 1.25)
        self.assertIn("status log line", result["data"]["recent_logs"])
        self.assertIn("🎯 자막 생성 중", result["data"]["recent_stage_logs"])

    def test_status_command_reuses_short_ttl_snapshot_for_polling(self):
        owner = _DummyOwner()
        with patch("ui.main.app_command_bridge._status_snapshot", wraps=app_bridge._status_snapshot) as snapshot:
            first = execute_app_command(owner, {"command": "status"})
            second = execute_app_command(owner, {"command": "status"})

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual(snapshot.call_count, 1)

    def test_status_command_uses_logger_combined_tail_helper(self):
        owner = _DummyOwner()
        logger = get_logger()
        logger.log("plain status line")
        logger.log("🎯 자막 생성 중")

        with patch.object(logger, "recent_lines_and_filtered", wraps=logger.recent_lines_and_filtered) as getter:
            result = execute_app_command(owner, {"command": "status"})

        self.assertTrue(result["ok"])
        getter.assert_called_once()
        self.assertIn("plain status line", result["data"]["recent_logs"])
        self.assertIn("🎯 자막 생성 중", result["data"]["recent_stage_logs"])

    def test_guided_subtitle_status_reuses_short_ttl_snapshot_for_polling(self):
        owner = _DummyOwner()
        with patch("ui.main.app_command_bridge._status_snapshot", wraps=app_bridge._status_snapshot) as snapshot:
            first = execute_app_command(owner, {"command": "guided-subtitle-status"})
            second = execute_app_command(owner, {"command": "guided-subtitle-status"})

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual(snapshot.call_count, 1)

    def test_state_changing_command_clears_status_cache(self):
        owner = _DummyOwner()
        execute_app_command(owner, {"command": "status"})
        execute_app_command(owner, {"command": "editor-set-playhead", "options": {"sec": 1.5}})

        result = execute_app_command(owner, {"command": "status"})

        self.assertTrue(result["ok"])
        self.assertAlmostEqual(result["data"]["editor_runtime"]["playhead_sec"], 1.5)

    def test_editor_set_playhead_command_updates_editor_runtime(self):
        owner = _DummyOwner()

        result = execute_app_command(owner, {"command": "editor-set-playhead", "options": {"sec": 1.25, "center": True}})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "editor_playhead_set")
        self.assertAlmostEqual(owner._editor_widget._playhead_sec, 1.25)
        self.assertAlmostEqual(result["data"]["editor_runtime"]["playhead_sec"], 1.25)

    def test_editor_pin_shadow_playhead_command_updates_runtime(self):
        owner = _DummyOwner()
        owner._editor_widget._playhead_sec = 1.25

        result = execute_app_command(owner, {"command": "editor-pin-shadow-playhead", "options": {}})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "editor_shadow_playhead_pinned")
        self.assertAlmostEqual(owner._editor_widget._shadow_playhead_sec, 1.25)
        self.assertTrue(result["data"]["editor_runtime"]["shadow_playhead_active"])

    def test_editor_clear_shadow_playhead_command_updates_runtime(self):
        owner = _DummyOwner()
        owner._editor_widget._shadow_playhead_sec = 1.25

        result = execute_app_command(owner, {"command": "editor-clear-shadow-playhead"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "editor_shadow_playhead_cleared")
        self.assertIsNone(owner._editor_widget._shadow_playhead_sec)
        self.assertFalse(result["data"]["editor_runtime"]["shadow_playhead_active"])

    def test_editor_zoom_max_command_sets_max_pps(self):
        owner = _DummyOwner()

        result = execute_app_command(owner, {"command": "editor-zoom-max"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "editor_zoom_max_applied")
        self.assertAlmostEqual(owner._editor_widget._timeline_pps, 500.0)
        self.assertAlmostEqual(result["data"]["editor_runtime"]["timeline_pps"], 500.0)

    def test_editor_playback_play_command_marks_center_lock(self):
        owner = _DummyOwner()

        result = execute_app_command(owner, {"command": "editor-playback", "options": {"action": "play"}})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "editor_playback_play")
        self.assertTrue(owner._editor_widget._playing)
        self.assertTrue(result["data"]["editor_runtime"]["playback_center_lock"])

    def test_editor_move_segment_left_command_can_preselect_line(self):
        owner = _DummyOwner()
        owner._editor_widget._playhead_sec = 0.4

        result = execute_app_command(
            owner,
            {"command": "editor-move-segment-left", "options": {"line": 1}},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "editor_segment_left_moved")
        self.assertAlmostEqual(owner._editor_widget._segments[1]["start"], 0.4)
        self.assertEqual(result["data"]["selected"]["selected_line"], 1)

    def test_editor_move_diamond_command_updates_adjacent_boundary(self):
        owner = _DummyOwner()
        owner._editor_widget._playhead_sec = 1.35

        result = execute_app_command(
            owner,
            {"command": "editor-move-diamond", "options": {"line": 0, "side": "right"}},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "editor_diamond_moved")
        self.assertAlmostEqual(owner._editor_widget._segments[0]["end"], 1.35)
        self.assertAlmostEqual(owner._editor_widget._segments[1]["start"], 1.35)

    def test_editor_begin_smart_split_command_enters_split_mode(self):
        owner = _DummyOwner()
        owner._editor_widget._playhead_sec = 1.5

        result = execute_app_command(
            owner,
            {"command": "editor-begin-smart-split", "options": {"line": 1}},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "editor_smart_split_mode_started")
        self.assertTrue(owner._editor_widget._inline_edit_active)
        self.assertAlmostEqual(owner._editor_widget._split_pending_sec, 1.5)
        self.assertEqual(result["data"]["editor_runtime"]["inline_edit_mode"], "smart_split")

    def test_editor_set_inline_cursor_command_updates_runtime_snapshot(self):
        owner = _DummyOwner()
        owner._editor_widget._playhead_sec = 1.5
        execute_app_command(owner, {"command": "editor-begin-smart-split", "options": {"line": 1}})

        result = execute_app_command(owner, {"command": "editor-set-inline-cursor", "options": {"position": 2}})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "editor_inline_cursor_set")
        self.assertEqual(owner._editor_widget._inline_cursor, 2)
        self.assertEqual(result["data"]["editor_runtime"]["inline_edit_cursor"], 2)
        self.assertEqual(result["data"]["editor_runtime"]["inline_edit_text"], "둘째 줄")

    def test_editor_commit_inline_edit_command_finishes_pending_split(self):
        owner = _DummyOwner()
        owner._editor_widget._playhead_sec = 1.5
        execute_app_command(owner, {"command": "editor-begin-smart-split", "options": {"line": 1}})
        execute_app_command(owner, {"command": "editor-set-inline-cursor", "options": {"position": 2}})

        result = execute_app_command(owner, {"command": "editor-commit-inline-edit"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "editor_inline_edit_committed")
        self.assertFalse(owner._editor_widget._inline_edit_active)
        self.assertEqual(len(owner._editor_widget._segments), 3)
        self.assertEqual(owner._editor_widget._segments[1]["text"], "둘째")
        self.assertEqual(owner._editor_widget._segments[2]["text"], "줄")

    def test_editor_smart_split_command_splits_selected_segment_at_playhead(self):
        owner = _DummyOwner()
        owner._editor_widget._playhead_sec = 0.5

        result = execute_app_command(
            owner,
            {"command": "editor-smart-split", "options": {"line": 0}},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "editor_smart_split_done")
        self.assertEqual(len(owner._editor_widget._segments), 3)
        self.assertAlmostEqual(owner._editor_widget._segments[0]["end"], 0.5)
        self.assertAlmostEqual(owner._editor_widget._segments[1]["start"], 0.5)

    def test_status_command_logs_nonfatal_queue_snapshot_failures(self):
        owner = _DummyOwner()

        def _broken_queue_completion_state():
            raise RuntimeError("queue snapshot boom")

        owner.queue_completion_state = _broken_queue_completion_state

        result = execute_app_command(owner, {"command": "status"})

        self.assertTrue(result["ok"])
        self.assertTrue(
            any(
                "앱 자동화 실패 [queue completion snapshot]" in line
                for line in get_logger().recent_lines(10)
            )
        )

    def test_capture_snapshot_command_saves_default_png_under_output_dir(self):
        owner = _DummyOwner()
        with tempfile.TemporaryDirectory() as tmp:
            with patch("ui.main.app_command_bridge.config.OUTPUT_DIR", tmp):
                result = execute_app_command(owner, {"command": "capture-snapshot", "options": {"async": False}})
                self.assertTrue(result["ok"])
                saved_path = result["data"]["path"]
                self.assertTrue(saved_path.endswith(".png"))
                self.assertIn(os.path.join(tmp, "app_snapshots"), saved_path)
                self.assertTrue(os.path.isfile(saved_path))
                self.assertEqual(result["data"]["width"], 640)
                self.assertEqual(result["data"]["height"], 360)

    def test_capture_snapshot_command_uses_explicit_path_and_appends_png_extension(self):
        owner = _DummyOwner()
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "manual_capture")
            result = execute_app_command(owner, {"command": "snapshot", "path": target, "options": {"async": False}})
            self.assertTrue(result["ok"])
            self.assertEqual(result["data"]["path"], f"{target}.png")
            self.assertTrue(os.path.isfile(f"{target}.png"))

    def test_capture_snapshot_command_accepts_directory_target(self):
        owner = _DummyOwner()
        with tempfile.TemporaryDirectory() as tmp:
            result = execute_app_command(owner, {"command": "capture-snapshot", "path": tmp, "options": {"async": False}})
            self.assertTrue(result["ok"])
            saved_path = result["data"]["path"]
            self.assertTrue(saved_path.startswith(tmp + os.sep))
            self.assertTrue(os.path.isfile(saved_path))

    def test_capture_snapshot_command_reports_save_failure(self):
        owner = _DummyOwner()
        owner.grab = lambda: _DummyPixmap(save_ok=False)

        result = execute_app_command(owner, {"command": "capture-snapshot", "path": "/tmp/fail_capture.png", "options": {"async": False}})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "snapshot_save_failed")

    def test_capture_snapshot_command_can_queue_async_capture(self):
        owner = _DummyOwner()
        result = execute_app_command(owner, {"command": "capture-snapshot", "path": "/tmp/queued_capture.png"})

        self.assertTrue(result["ok"])
        self.assertTrue(result["queued"])
        self.assertEqual(result["message"], "snapshot_queued")
        self.assertEqual(result["data"]["path"], "/tmp/queued_capture.png")
        self.assertEqual(owner.async_snapshot_requests[0]["path"], "/tmp/queued_capture.png")

    def test_open_dictionary_command_shows_nonmodal_dictionary(self):
        owner = _DummyOwner()

        result = execute_app_command(owner, {"command": "open-dictionary"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "dictionary_visible")
        self.assertEqual(owner.dictionary_dialog_opened, 1)
        self.assertIsNotNone(owner._correction_dictionary_dialog)

    def test_capture_dictionary_snapshot_command_saves_dialog_png(self):
        owner = _DummyOwner()
        owner._correction_dictionary_dialog = _DummyVisibleDialog()

        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "dictionary_capture.png")
            result = execute_app_command(owner, {"command": "capture-dictionary-snapshot", "path": target})
            self.assertTrue(os.path.isfile(target))

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "dictionary_snapshot_captured")
        self.assertEqual(result["data"]["path"], target)
        self.assertEqual(result["data"]["width"], 1960)
        self.assertEqual(result["data"]["height"], 1280)

    def test_capture_dictionary_snapshot_command_requires_visible_dialog(self):
        owner = _DummyOwner()
        owner._correction_dictionary_dialog = _DummyVisibleDialog(visible=False)

        result = execute_app_command(owner, {"command": "capture-dictionary-snapshot", "path": "/tmp/dictionary_capture.png"})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "dictionary_not_visible")

    def test_guided_subtitle_run_opens_media_starts_pipeline_and_captures_initial_snapshots(self):
        owner = _DummyOwner()
        with tempfile.TemporaryDirectory() as tmp:
            media_path = Path(tmp) / "demo.mp4"
            media_path.write_bytes(b"video")

            result = execute_app_command(
                owner,
                {"command": "guided-subtitle-run", "path": str(media_path), "options": {"snapshot_dir": "/tmp/snaps"}},
            )

        self.assertTrue(result["ok"])
        self.assertEqual(owner.guided_runs, [(str(media_path), "/tmp/snaps")])
        self.assertEqual(owner._editor_widget.start_clicks, 1)
        self.assertEqual(owner.backend_start_calls, [{"files": [str(media_path)], "folder": None, "is_icloud": False, "is_auto_start": True}])
        self.assertEqual([item["label"] for item in owner.guided_snapshots], ["opened", "pipeline-started"])
        self.assertEqual(result["data"]["snapshot_dir"], "/tmp/snaps")


if __name__ == "__main__":
    unittest.main()
