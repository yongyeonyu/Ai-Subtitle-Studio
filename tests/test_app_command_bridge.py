import errno
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.runtime.logger import get_logger
from core.runtime.stage_metrics import record_stage_done, reset_stage_metrics
import ui.main.app_command_bridge as app_bridge
from ui.main.app_command_bridge import dispatch_app_command, execute_app_command


class _DummyEditor:
    def __init__(self, state: str = "ST_IDLE"):
        self.media_path = "/tmp/media.mp4"
        self.video_fps = 30.0
        self.sm = SimpleNamespace(state=state)
        self.settings = {}
        self.start_clicks = 0
        self.save_calls = 0
        self.roughcut_starts = 0
        self.roughcut_manual = False
        self._on_start_callback = None
        self._playhead_sec = 0.0
        self._shadow_playhead_sec = None
        self._selected_line = 0
        self._inline_edit_active = False
        self._split_pending_sec = None
        self._inline_text = ""
        self._inline_cursor = None
        self._timeline_pps = 12.0
        self._timeline_fit_locked = False
        self._time_window_applied = False
        self._playback_center_lock = False
        self._playing = False
        self._video_visible = True
        self._active_footer_menu_id = "video"
        self._stt_mode_enabled = False
        self._stt_state = "disabled"
        self._stt_recording = False
        self._stt_vad_running = False
        self._last_saved_srt_outputs = []
        self.flush_calls = 0
        self._pending_flush_segments = None
        self._segments = [
            {"line": 0, "start": 0.0, "end": 1.0, "text": "첫 줄", "is_gap": False},
            {"line": 1, "start": 1.0, "end": 2.0, "text": "둘째 줄", "is_gap": False},
        ]

    def _on_start_clicked(self):
        self.start_clicks += 1
        callback = getattr(self, "_on_start_callback", None)
        if callable(callback):
            callback()

    def _on_save(self, skip_auto_next=True, auto_export=False):
        self.save_calls += 1
        if not self._last_saved_srt_outputs:
            srt_path = "/tmp/media.srt"
            Path(srt_path).write_text("dummy srt", encoding="utf-8")
            self._last_saved_srt_outputs = [(srt_path, self.media_path)]
        return True

    def _get_current_segments(self):
        return list(self._segments)

    def _flush_pending_segment_queue_now(self):
        self.flush_calls += 1
        if self._pending_flush_segments is not None:
            self._segments = [dict(seg) for seg in list(self._pending_flush_segments or [])]
            self._pending_flush_segments = None

    def _segments_for_srt_output(self, segs):
        return list(segs or [])

    def _schedule_post_generation_roughcut_draft(self, force: bool = False):
        self.roughcut_starts += 1
        self.roughcut_force = bool(force)

    def _run_manual_roughcut_llm_from_global_canvas(self):
        self.roughcut_manual = True
        self._schedule_post_generation_roughcut_draft(force=True)

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
            "time_window_applied": self._time_window_applied,
            "timeline_scroll_x": 0.0,
            "timeline_fit_locked": self._timeline_fit_locked,
            "playback_center_lock": self._playback_center_lock,
            "video_visible": bool(self._video_visible),
            "active_footer_menu_id": str(self._active_footer_menu_id),
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
        self._timeline_fit_locked = False
        return {
            "timeline_pps": self._timeline_pps,
            "editor_runtime": self.automation_editor_state_snapshot(),
        }

    def automation_timeline_view_action(self, action: str):
        normalized = str(action or "").strip().lower()
        previous = self._timeline_pps
        if normalized == "zoom-in":
            self._timeline_pps *= 1.25
            self._timeline_fit_locked = False
        elif normalized == "zoom-out":
            self._timeline_pps /= 1.25
            self._timeline_fit_locked = False
        elif normalized == "fit":
            self._timeline_pps = 8.0
            self._timeline_fit_locked = True
        elif normalized == "time-window":
            self._timeline_pps = 64.0
            self._timeline_fit_locked = False
            self._time_window_applied = True
        elif normalized == "max":
            self._timeline_pps = 500.0
            self._timeline_fit_locked = False
        else:
            raise ValueError("timeline_view_action_unavailable")
        return {
            "action": normalized,
            "previous_timeline_pps": previous,
            "timeline_pps": self._timeline_pps,
            "timeline_fit_locked": self._timeline_fit_locked,
            "editor_runtime": self.automation_editor_state_snapshot(),
        }

    def automation_run_subtitle_magnet(self):
        before = self.automation_editor_state_snapshot()
        self._segments[0]["end"] = self._segments[1]["start"]
        after = self.automation_editor_state_snapshot()
        return {
            "changed": True,
            "before_segment_count": int(before["segment_count"]),
            "after_segment_count": int(after["segment_count"]),
            "before_gap_count": int(before["gap_count"]),
            "after_gap_count": int(after["gap_count"]),
            "editor_runtime": after,
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

    def automation_set_video_visible(self, action: str):
        normalized = str(action or "toggle")
        if normalized == "toggle":
            self._video_visible = not self._video_visible
        elif normalized == "show":
            self._video_visible = True
        elif normalized == "hide":
            self._video_visible = False
        else:
            raise ValueError("invalid_video_action")
        self._active_footer_menu_id = "video" if self._video_visible else ""
        return {
            "action": normalized,
            "video_visible": bool(self._video_visible),
            "active_footer_menu_id": str(self._active_footer_menu_id),
            "editor_runtime": self.automation_editor_state_snapshot(),
        }

    def _auto_export_saved_subtitle_videos(self, *, outputs=None):
        export_outputs = list(outputs if outputs is not None else self._last_saved_srt_outputs)
        for _srt_path, target_file in export_outputs:
            mov_path = Path(target_file).with_name(f"{Path(target_file).stem}_자막소스.mov")
            mov_path.write_bytes(b"mov")

    def _set_stt_mode_enabled(self, enabled: bool):
        self._stt_mode_enabled = bool(enabled)
        self._stt_state = "ready_to_listen" if enabled else "disabled"

    def _toggle_stt_mode(self):
        self._set_stt_mode_enabled(not self._stt_mode_enabled)

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
        selection_source = "requested"
        if not float(seg["start"]) + 0.05 < float(self._playhead_sec) < float(seg["end"]) - 0.05:
            fallback_idx = self._segment_index(at_playhead=True)
            if fallback_idx is not None and fallback_idx != idx:
                fallback = self._segments[fallback_idx]
                if float(fallback["start"]) + 0.05 < float(self._playhead_sec) < float(fallback["end"]) - 0.05:
                    selected = self.automation_select_segment(at_playhead=True)
                    idx = fallback_idx
                    seg = self._segments[idx]
                    selection_source = "playhead_fallback"
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
            "selection_source": selection_source,
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
        self.saved_project_segments = None
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
        self.settings_dialog_opened = 0
        self.speaker_dialog_opened = 0
        self.personalization_actions = []
        self._automation_active_dialog = None
        self._correction_dictionary_dialog = None
        self.backend = SimpleNamespace(
            _active=False,
            start_pipeline=self._start_pipeline,
            start_multiclip_pipeline=self._start_multiclip_pipeline,
            _force_no_reuse_once=False,
            _force_reuse_existing_multiclip_subtitles_once=False,
        )
        self._sig_external_app_command = SimpleNamespace(emit=lambda payload, state=None: None)
        self._editor_widget = _DummyEditor()
        self._roughcut_widget = _DummyRoughcutWidget()
        self.global_menu_bar = _DummyGlobalMenuBar(self)
        self.last_open_args = None
        self.roughcut_open_calls = 0

    def show_home(self, allow_home_idle_learning: bool = False):
        self.home_calls += 1

    def _open_project_file(self, path: str) -> bool:
        self.opened_project = path
        return True

    def _open_roughcut_helper(self):
        self.roughcut_open_calls += 1
        self._current_work_mode = "roughcut"

    def _start_queue_mode(self, files, folder=None, source="queue"):
        self.queue_calls.append((list(files), folder, source))

    def _save_current_project(self, segments=None):
        self.saved_project += 1
        self.saved_project_segments = list(segments or []) if segments is not None else None

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

    def _run_personalization_idle_jobs_now(self):
        self.personalization_actions.append("run-now")
        return {"started": True, "action": "run-now"}

    def _pause_personalization_idle_jobs(self):
        self.personalization_actions.append("pause")
        return {"paused": True}

    def _resume_personalization_idle_jobs(self):
        self.personalization_actions.append("resume")
        return {"resumed": True}


class _DummyGlobalMenuBar:
    def __init__(self, owner):
        self.owner = owner
        self.actions = []
        self._actions = {
            "left_설정": ("설정", True),
            "left_화자": ("화자", True),
            "left_사전": ("사전", True),
            "left_비디오": ("비디오", True),
            "left_음성": ("음성", True),
            "center_save": ("저장", True),
            "right_quit": ("종료", True),
        }

    def automation_trigger_action(self, action_id: str):
        normalized = str(action_id or "")
        if normalized == "center_save":
            self.owner._editor_widget._on_save(skip_auto_next=True)
        elif normalized in {"left_설정", "left_화자", "left_사전"}:
            pass
        elif normalized == "left_비디오":
            self.owner._editor_widget.automation_set_video_visible("toggle")
        elif normalized == "left_음성":
            self.owner._editor_widget._toggle_stt_mode()
        else:
            raise ValueError("global_menu_action_missing")
        self.actions.append(normalized)
        return {
            "action_id": normalized,
            "text": normalized,
            "enabled": True,
            "trigger_count": len(self.actions),
        }

    def automation_action_snapshot(self):
        actions = [
            {"action_id": action_id, "text": text, "enabled": enabled}
            for action_id, (text, enabled) in sorted(self._actions.items())
        ]
        return {"action_count": len(actions), "actions": actions}


class _DummyRoughcutWidget:
    def __init__(self):
        self.selected_candidate_id = "candidate_current"
        self.candidate_ids = ["candidate_current", "candidate_prev_1", "candidate_prev_2"]
        self.selected_chapter_id = "chapter_0001"
        self.selected_segment_id = "major_A"
        self.segment_order = ["major_A", "major_B", "major_C"]
        self.chapter_order = ["chapter_0001", "chapter_0002", "chapter_0003"]
        self.filter_value = "전체"
        self.video_host_attached = True
        self.player_menu_visible = True
        self.sequence_preview_active = False
        self.render_video_targets = []

    def automation_runtime_snapshot(self):
        return {
            "has_result": True,
            "selected_candidate_id": self.selected_candidate_id,
            "candidate_count": len(self.candidate_ids),
            "candidate_ids": list(self.candidate_ids),
            "selected_chapter_id": self.selected_chapter_id,
            "selected_segment_id": self.selected_segment_id,
            "selected_chapter_title": f"title:{self.selected_chapter_id}",
            "candidate_state": "현재 자막 기준",
            "filter_value": self.filter_value,
            "filter_summary": f"표시 {len(self.chapter_order)} / 전체 {len(self.chapter_order)}",
            "selection_summary": f"선택 {self.selected_chapter_id} · 확정",
            "order_summary": f"카드 {self.segment_order.index(self.selected_segment_id) + 1}/{len(self.segment_order)} · {' > '.join(self.segment_order[:5])}",
            "sequence_preview_active": bool(self.sequence_preview_active),
            "visible_row_count": len(self.chapter_order),
            "total_row_count": len(self.chapter_order),
            "visible_chapter_ids": list(self.chapter_order),
            "visible_segment_ids": list(self.segment_order),
            "chapter_order": list(self.chapter_order),
            "segment_order": list(self.segment_order),
            "chapter_order_state": list(self.chapter_order),
            "video_host_attached": self.video_host_attached,
            "video_placeholder_visible": False,
            "player_menu_visible": self.player_menu_visible,
        }

    def automation_select_candidate(self, *, candidate_id: str = "", index: int | None = None):
        if index is not None:
            if index < 0 or index >= len(self.candidate_ids):
                raise ValueError("roughcut_candidate_index_out_of_range")
            self.selected_candidate_id = self.candidate_ids[index]
        elif candidate_id:
            if candidate_id not in self.candidate_ids:
                raise ValueError("roughcut_candidate_not_found")
            self.selected_candidate_id = candidate_id
        else:
            raise ValueError("roughcut_candidate_missing")
        return self.automation_runtime_snapshot()

    def automation_select_chapter(self, *, chapter_id: str = "", row: int | None = None, autoplay: bool = False):
        if row is not None:
            if row < 0 or row >= len(self.chapter_order):
                raise ValueError("roughcut_row_out_of_range")
            self.selected_chapter_id = self.chapter_order[row]
        elif chapter_id:
            if chapter_id not in self.chapter_order:
                raise ValueError("roughcut_chapter_not_found")
            self.selected_chapter_id = chapter_id
        else:
            raise ValueError("roughcut_chapter_missing")
        data = self.automation_runtime_snapshot()
        data["autoplay"] = bool(autoplay)
        return data

    def automation_move_selected_chapter(self, delta: int):
        if self.selected_chapter_id not in self.chapter_order:
            raise ValueError("roughcut_selection_missing")
        current = self.chapter_order.index(self.selected_chapter_id)
        target = max(0, min(len(self.chapter_order) - 1, current + int(delta)))
        item = self.chapter_order.pop(current)
        self.chapter_order.insert(target, item)
        data = self.automation_runtime_snapshot()
        data["changed"] = target != current
        data["target_index"] = target
        return data

    def automation_move_selected_segment(self, delta: int):
        if self.selected_segment_id not in self.segment_order:
            raise ValueError("roughcut_segment_selection_missing")
        current = self.segment_order.index(self.selected_segment_id)
        target = max(0, min(len(self.segment_order) - 1, current + int(delta)))
        item = self.segment_order.pop(current)
        self.segment_order.insert(target, item)
        data = self.automation_runtime_snapshot()
        data["changed"] = target != current
        data["target_index"] = target
        return data

    def automation_start_preview_sequence(self):
        self.sequence_preview_active = True
        return self.automation_runtime_snapshot()

    def automation_set_safety_filter(self, value: str):
        if value not in {"전체", "ideal", "acceptable", "risky"}:
            raise ValueError("roughcut_filter_invalid")
        self.filter_value = value
        return self.automation_runtime_snapshot()

    def export_roughcut_srt_to_path(self, path: str):
        target = Path(path or "/tmp/roughcut_export.srt")
        target.write_text("1\n00:00:00,000 --> 00:00:01,000\n테스트\n", encoding="utf-8")
        return {"path": str(target), "subtitle_count": 1}

    def automation_start_render_video_to_path(self, path: str = ""):
        target = Path(path or "/tmp/roughcut_render.mp4")
        self.render_video_targets.append(str(target))
        return {
            "path": str(target),
            "render_plan_path": str(target.with_name(f"{target.stem}_render_plan.json")),
            "edl_path": str(target.with_name(f"{target.stem}_edl.json")),
            "stitched_cut_boundary_count": 1,
            "render_mode": "sync_safe",
            "extract_command_count": 2,
            "concat_command_count": 1,
        }


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

    def setModal(self, visible: bool):
        self._modal = bool(visible)

    def show(self):
        self._visible = True

    def raise_(self):
        return None

    def activateWindow(self):
        return None

    def close(self):
        self._visible = False

    def grab(self):
        return self._pixmap


class AppCommandBridgeTests(unittest.TestCase):
    def setUp(self):
        clearer = getattr(get_logger(), "clear_recent_lines", None)
        if callable(clearer):
            clearer()
        app_bridge._clear_status_snapshot_cache()
        reset_stage_metrics()

    def test_open_project_command_uses_path_based_helper(self):
        owner = _DummyOwner()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo.json"
            path.write_text("{}", encoding="utf-8")

            result = execute_app_command(owner, {"command": "open-project", "path": str(path)})

        self.assertTrue(result["ok"])
        self.assertEqual(owner.opened_project, str(path))

    def test_open_project_command_classifies_permission_error(self):
        owner = _DummyOwner()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo.json"
            path.write_text("{}", encoding="utf-8")

            def _deny(_path):
                raise PermissionError(errno.EPERM, "Operation not permitted", str(path))

            owner._open_project_file = _deny

            result = execute_app_command(owner, {"command": "open-project", "path": str(path)})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "project_open_permission_denied")
        self.assertEqual(result["data"]["path"], str(path))

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

    def test_save_project_command_passes_current_editor_segments_for_open_project(self):
        owner = _DummyOwner()
        owner._current_project_path = "/tmp/project.json"
        owner._editor_widget._segments = [
            {"line": 0, "start": 1.0, "end": 2.2, "text": "merged row", "is_gap": False},
            {"line": 1, "start": 3.0, "end": 4.3, "text": "next row", "is_gap": False},
        ]

        result = execute_app_command(owner, {"command": "save-project"})

        self.assertTrue(result["ok"])
        self.assertEqual(owner.saved_project, 1)
        self.assertEqual(owner._editor_widget.save_calls, 0)
        self.assertEqual([row["text"] for row in owner.saved_project_segments], ["merged row", "next row"])

    def test_save_project_command_flushes_pending_editor_rows_before_project_save(self):
        owner = _DummyOwner()
        owner._current_project_path = "/tmp/project.json"
        owner._editor_widget._pending_flush_segments = [
            {"line": 0, "start": 1.0, "end": 2.2, "text": "flushed merged row", "is_gap": False},
            {"line": 1, "start": 3.0, "end": 4.3, "text": "flushed next row", "is_gap": False},
        ]

        result = execute_app_command(owner, {"command": "save-project"})

        self.assertTrue(result["ok"])
        self.assertEqual(owner._editor_widget.flush_calls, 1)
        self.assertEqual(
            [row["text"] for row in owner.saved_project_segments],
            ["flushed merged row", "flushed next row"],
        )

    def test_save_subtitles_command_returns_saved_outputs(self):
        owner = _DummyOwner()

        result = execute_app_command(owner, {"command": "save-subtitles"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "subtitles_saved")
        self.assertEqual(result["data"]["count"], 1)
        self.assertTrue(result["data"]["outputs"][0]["exists"])

    def test_save_subtitles_command_reports_missing_segments_before_save(self):
        owner = _DummyOwner()
        owner._editor_widget._segments = []

        result = execute_app_command(owner, {"command": "save-subtitles"})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "subtitle_segments_missing")
        self.assertEqual(result["data"]["segment_count"], 0)
        self.assertEqual(owner._editor_widget.save_calls, 0)

    def test_export_subtitles_command_writes_requested_path(self):
        owner = _DummyOwner()
        with tempfile.TemporaryDirectory() as tmp:
            export_path = Path(tmp) / "manual_export.srt"

            result = execute_app_command(owner, {"command": "export-subtitles", "path": str(export_path)})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "subtitles_exported")
        self.assertEqual(result["data"]["output"]["path"], str(export_path))
        self.assertTrue(result["data"]["output"]["exists"])

    def test_export_subtitle_video_command_writes_mov_outputs(self):
        owner = _DummyOwner()
        with tempfile.TemporaryDirectory() as tmp:
            media_path = Path(tmp) / "demo.mp4"
            media_path.write_bytes(b"video")
            srt_path = Path(tmp) / "demo.srt"
            srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\n테스트\n", encoding="utf-8")
            owner._editor_widget.media_path = str(media_path)
            owner._editor_widget._last_saved_srt_outputs = [(str(srt_path), str(media_path))]

            result = execute_app_command(owner, {"command": "export-subtitle-video"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "subtitle_videos_exported")
        self.assertEqual(result["data"]["count"], 1)
        self.assertTrue(result["data"]["outputs"][0]["mov_output"]["exists"])

    def test_export_subtitle_video_command_queues_when_scheduler_is_available(self):
        owner = _DummyOwner()
        scheduled = []
        with tempfile.TemporaryDirectory() as tmp:
            media_path = Path(tmp) / "demo.mp4"
            media_path.write_bytes(b"video")
            srt_path = Path(tmp) / "demo.srt"
            srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\n테스트\n", encoding="utf-8")
            owner._editor_widget.media_path = str(media_path)
            owner._editor_widget._last_saved_srt_outputs = [(str(srt_path), str(media_path))]
            owner._editor_widget._schedule_auto_export_saved_subtitle_videos = lambda delay_ms=1500: scheduled.append(delay_ms)

            result = execute_app_command(owner, {"command": "export-subtitle-video"})

        self.assertTrue(result["ok"])
        self.assertTrue(result["queued"])
        self.assertEqual(result["message"], "subtitle_video_export_queued")
        self.assertEqual(scheduled, [0])
        self.assertEqual(result["data"]["count"], 1)

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
        self.assertTrue(owner._editor_widget.roughcut_manual)
        self.assertTrue(owner._editor_widget.roughcut_force)

    def test_open_roughcut_switches_work_mode(self):
        owner = _DummyOwner()

        result = execute_app_command(owner, {"command": "open-roughcut"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "roughcut_opened")
        self.assertEqual(owner.roughcut_open_calls, 1)
        self.assertEqual(owner._current_work_mode, "roughcut")
        self.assertEqual(result["data"]["current_work_mode"], "roughcut")

    def test_roughcut_select_chapter_returns_runtime_snapshot(self):
        owner = _DummyOwner()

        result = execute_app_command(owner, {"command": "roughcut-select-chapter", "options": {"chapter_id": "chapter_0002", "autoplay": True}})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "roughcut_chapter_selected")
        self.assertEqual(result["data"]["selected_chapter_id"], "chapter_0002")
        self.assertTrue(result["data"]["autoplay"])

    def test_roughcut_select_candidate_returns_runtime_snapshot(self):
        owner = _DummyOwner()

        result = execute_app_command(owner, {"command": "roughcut-select-candidate", "options": {"index": 1}})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "roughcut_candidate_selected")
        self.assertEqual(result["data"]["selected_candidate_id"], "candidate_prev_1")
        self.assertEqual(result["data"]["candidate_count"], 3)

    def test_roughcut_move_chapter_updates_order(self):
        owner = _DummyOwner()
        owner._roughcut_widget.selected_chapter_id = "chapter_0002"

        result = execute_app_command(owner, {"command": "roughcut-move-chapter", "options": {"direction": "down"}})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "roughcut_chapter_moved")
        self.assertEqual(result["data"]["chapter_order"], ["chapter_0001", "chapter_0003", "chapter_0002"])
        self.assertEqual(result["data"]["selected_chapter_id"], "chapter_0002")

    def test_roughcut_move_segment_updates_order(self):
        owner = _DummyOwner()
        owner._roughcut_widget.selected_segment_id = "major_B"

        result = execute_app_command(owner, {"command": "roughcut-move-segment", "options": {"direction": "down"}})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "roughcut_segment_moved")
        self.assertEqual(result["data"]["segment_order"], ["major_A", "major_C", "major_B"])
        self.assertEqual(result["data"]["selected_segment_id"], "major_B")
        self.assertEqual(result["data"]["order_summary"], "카드 3/3 · major_A > major_C > major_B")

    def test_roughcut_play_sequence_marks_sequence_active(self):
        owner = _DummyOwner()

        result = execute_app_command(owner, {"command": "roughcut-play-sequence"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "roughcut_sequence_started")
        self.assertTrue(result["data"]["sequence_preview_active"])

    def test_roughcut_set_safety_filter_updates_runtime(self):
        owner = _DummyOwner()

        result = execute_app_command(owner, {"command": "roughcut-set-safety-filter", "options": {"value": "risky"}})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "roughcut_filter_updated")
        self.assertEqual(result["data"]["filter_value"], "risky")

    def test_roughcut_export_srt_writes_output(self):
        owner = _DummyOwner()
        with tempfile.TemporaryDirectory() as tmp:
            export_path = Path(tmp) / "roughcut_export.srt"

            result = execute_app_command(owner, {"command": "roughcut-export-srt", "path": str(export_path)})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "roughcut_srt_exported")
        self.assertTrue(result["data"]["output"]["exists"])
        self.assertEqual(result["data"]["subtitle_count"], 1)

    def test_roughcut_render_video_queues_expected_outputs(self):
        owner = _DummyOwner()
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "roughcut_render.mp4"

            result = execute_app_command(owner, {"command": "roughcut-render-video", "path": str(output_path)})

        self.assertTrue(result["ok"])
        self.assertTrue(result["queued"])
        self.assertEqual(result["message"], "roughcut_render_started")
        self.assertEqual(owner._roughcut_widget.render_video_targets, [str(output_path)])
        self.assertEqual(result["data"]["path"], str(output_path))
        self.assertEqual(result["data"]["render_mode"], "sync_safe")
        self.assertEqual(result["data"]["output"]["path"], str(output_path))
        self.assertFalse(result["data"]["output"]["exists"])
        self.assertEqual(Path(result["data"]["render_plan_path"]).name, "roughcut_render_render_plan.json")
        self.assertEqual(Path(result["data"]["edl_path"]).name, "roughcut_render_edl.json")

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
        self.assertTrue(result["queued"])
        self.assertEqual(owner.multiclip_start_calls, [{"files": files, "folder": tmp}])
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
        self.assertTrue(result["queued"])
        self.assertTrue(owner.backend._force_no_reuse_once)
        self.assertFalse(owner.backend._force_reuse_existing_multiclip_subtitles_once)
        self.assertEqual(owner.multiclip_start_calls[0]["files"], [str(first), str(second)])

    def test_status_command_reports_current_runtime_snapshot(self):
        owner = _DummyOwner()
        owner._current_project_path = "/tmp/project.json"
        owner._runtime_resource_snapshot = {"rss_gb": 1.25, "pressure_stage": "normal", "timestamp": 1234.5}
        owner._editor_widget._last_live_processing_stage = "⏳ [STT+자막 LLM] 인식 결과 교정/분리 중"
        owner._editor_widget._roughcut_draft_status = "queued"
        owner._editor_widget._roughcut_draft_pending = True
        owner._automation_classify_guided_stage = lambda _text: ("subtitle-generation", "자막 생성")
        owner.backend._active = True
        get_logger().log("status log line")
        get_logger().log("🎯 자막 생성 중")

        result = execute_app_command(owner, {"command": "status"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["current_project_path"], "/tmp/project.json")
        self.assertTrue(result["data"]["backend_active"])
        self.assertTrue(result["data"]["editor_open"])
        self.assertEqual(result["data"]["editor_runtime"]["segment_count"], 2)
        self.assertEqual(result["data"]["generation_stage"], "⏳ [STT+자막 LLM] 인식 결과 교정/분리 중")
        self.assertEqual(result["data"]["last_stage_key"], "subtitle-generation")
        self.assertEqual(result["data"]["subtitle_count"], 2)
        self.assertTrue(result["data"]["roughcut_state"]["running"])
        self.assertEqual(result["data"]["roughcut_runtime"]["selected_chapter_id"], "chapter_0001")
        self.assertTrue(result["data"]["roughcut_runtime"]["video_host_attached"])
        self.assertEqual(result["data"]["runtime_timestamp"], 1234.5)
        self.assertEqual(result["data"]["runtime_resource"]["rss_gb"], 1.25)
        self.assertIn("stage_metrics", result["data"])
        self.assertIn("stage_metrics", result["data"]["runtime_resource"])
        self.assertIn("status log line", result["data"]["recent_logs"])
        self.assertIn("🎯 자막 생성 중", result["data"]["recent_stage_logs"])

    def test_status_snapshot_includes_stage_metrics_for_bottleneck_debugging(self):
        owner = _DummyOwner()
        record_stage_done(
            "app_command:guided-subtitle-status",
            resource_label="automation",
            wait_ms=3.5,
            worker_busy_ms=2.0,
            queue_depth=1,
            ok=True,
        )

        result = execute_app_command(owner, {"command": "guided-subtitle-status"})

        self.assertTrue(result["ok"])
        metrics = result["data"]["stage_metrics"]
        self.assertGreaterEqual(metrics["event_count"], 1)
        self.assertIn("automation", metrics["resources"])
        self.assertEqual(metrics["resources"]["automation"]["max_queue_depth"], 1)

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

    def test_dispatch_status_command_falls_back_without_waiting_for_busy_ui_thread(self):
        owner = _DummyOwner()
        owner.backend._active = True
        app_thread = object()
        current_thread = object()
        fake_app = SimpleNamespace(thread=lambda: app_thread)

        with patch("ui.main.app_command_bridge.QApplication.instance", return_value=fake_app):
            with patch("ui.main.app_command_bridge.QThread.currentThread", return_value=current_thread):
                result = dispatch_app_command(owner, {"command": "status"}, timeout_sec=1.0)

        self.assertTrue(result["ok"])
        self.assertTrue(result["accepted"])
        self.assertTrue(result["data"]["status_snapshot_fallback"])
        self.assertIn("backend_active", result["data"])

    def test_dispatch_status_command_skips_signal_when_busy_owner_has_no_cache(self):
        owner = _DummyOwner()
        owner._editor_widget.sm.state = "ST_PROC"
        owner._runtime_resource_snapshot = {"active_labels": ["pipeline"], "pressure_stage": "warning"}
        app_thread = object()
        current_thread = object()
        fake_app = SimpleNamespace(thread=lambda: app_thread)
        signal = SimpleNamespace(emit=lambda *_args, **_kwargs: self.fail("status signal should be skipped while busy"))
        owner._sig_external_app_command = signal

        with patch("ui.main.app_command_bridge.QApplication.instance", return_value=fake_app):
            with patch("ui.main.app_command_bridge.QThread.currentThread", return_value=current_thread):
                result = dispatch_app_command(owner, {"command": "guided-subtitle-status"}, timeout_sec=1.0)

        self.assertTrue(result["ok"])
        self.assertTrue(result["data"]["status_snapshot_fallback"])
        self.assertEqual(result["data"]["editor_state"], "ST_PROC")
        self.assertIsInstance(result["data"]["guided_snapshot_run"], dict)

    def test_dispatch_status_busy_fallback_uses_cached_runtime_resource_only(self):
        owner = _DummyOwner()
        owner._runtime_resource_snapshot = {"active_labels": ["pipeline"], "pressure_stage": "warning"}
        app_thread = object()
        current_thread = object()
        fake_app = SimpleNamespace(thread=lambda: app_thread)
        signal = SimpleNamespace(emit=lambda *_args, **_kwargs: self.fail("status signal should be skipped for active runtime labels"))
        owner._sig_external_app_command = signal

        with patch("ui.main.app_command_bridge.QApplication.instance", return_value=fake_app):
            with patch("ui.main.app_command_bridge.QThread.currentThread", return_value=current_thread):
                with patch("ui.main.app_command_bridge._runtime_resource_snapshot", side_effect=AssertionError("fresh snapshot forbidden")):
                    result = dispatch_app_command(owner, {"command": "status"}, timeout_sec=1.0)

        self.assertTrue(result["ok"])
        self.assertTrue(result["data"]["status_snapshot_fallback"])
        self.assertEqual(result["data"]["runtime_resource"]["pressure_stage"], "warning")

    def test_dispatch_status_command_caches_busy_fallback_snapshot(self):
        owner = _DummyOwner()
        owner._editor_widget.sm.state = "ST_PROC"
        owner._runtime_resource_snapshot = {"active_labels": ["pipeline"], "pressure_stage": "warning"}
        app_thread = object()
        current_thread = object()
        fake_app = SimpleNamespace(thread=lambda: app_thread)
        signal = SimpleNamespace(emit=lambda *_args, **_kwargs: self.fail("status signal should be skipped while busy"))
        owner._sig_external_app_command = signal

        with patch("ui.main.app_command_bridge.QApplication.instance", return_value=fake_app):
            with patch("ui.main.app_command_bridge.QThread.currentThread", return_value=current_thread):
                first = dispatch_app_command(owner, {"command": "status"}, timeout_sec=1.0)
                second = dispatch_app_command(owner, {"command": "ping"}, timeout_sec=1.0)

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual(second["message"], "pong")
        self.assertEqual(second["data"]["editor_state"], "ST_PROC")
        self.assertTrue(second["data"]["status_snapshot_fallback"])

    def test_dispatch_status_command_reuses_stale_cache_while_busy(self):
        owner = _DummyOwner()
        owner._editor_widget.sm.state = "ST_PROC"
        owner._runtime_resource_snapshot = {"active_labels": ["pipeline"], "pressure_stage": "warning"}
        app_thread = object()
        current_thread = object()
        fake_app = SimpleNamespace(thread=lambda: app_thread)
        signal = SimpleNamespace(emit=lambda *_args, **_kwargs: self.fail("busy stale cache should avoid signal"))
        owner._sig_external_app_command = signal
        app_bridge._store_status_snapshot(owner, {"editor_state": "ST_PROC", "backend_active": True, "guided_snapshot_run": {"active": True}})

        with patch("ui.main.app_command_bridge.QApplication.instance", return_value=fake_app):
            with patch("ui.main.app_command_bridge.QThread.currentThread", return_value=current_thread):
                with patch("ui.main.app_command_bridge._peek_status_snapshot_cache") as peek_cache:
                    peek_cache.side_effect = [
                        None,
                        (1.75, {"editor_state": "ST_PROC", "backend_active": True, "guided_snapshot_run": {"active": True}}),
                    ]
                    with patch("ui.main.app_command_bridge._status_fallback_snapshot") as fallback_snapshot:
                        result = dispatch_app_command(owner, {"command": "status"}, timeout_sec=1.0)

        self.assertTrue(result["ok"])
        self.assertTrue(result["data"]["status_snapshot_fallback"])
        self.assertEqual(result["data"]["status_snapshot_age_sec"], 1.75)
        self.assertTrue(result["data"]["guided_snapshot_run"]["active"])
        fallback_snapshot.assert_not_called()

    def test_dispatch_status_command_does_not_reuse_overdue_stale_cache_while_busy(self):
        owner = _DummyOwner()
        owner._editor_widget.sm.state = "ST_PROC"
        owner._runtime_resource_snapshot = {"active_labels": ["pipeline"], "pressure_stage": "warning"}
        app_thread = object()
        current_thread = object()
        fake_app = SimpleNamespace(thread=lambda: app_thread)
        signal = SimpleNamespace(emit=lambda *_args, **_kwargs: self.fail("overdue stale cache should still avoid signal"))
        owner._sig_external_app_command = signal

        with patch("ui.main.app_command_bridge.QApplication.instance", return_value=fake_app):
            with patch("ui.main.app_command_bridge.QThread.currentThread", return_value=current_thread):
                with patch("ui.main.app_command_bridge._peek_status_snapshot_cache") as peek_cache:
                    peek_cache.side_effect = [
                        None,
                        None,
                    ]
                    with patch("ui.main.app_command_bridge._status_fallback_snapshot", return_value={"editor_state": "ST_PROC", "guided_snapshot_run": {"active": True}}) as fallback_snapshot:
                        result = dispatch_app_command(owner, {"command": "guided-subtitle-status"}, timeout_sec=1.0)

        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["editor_state"], "ST_PROC")
        self.assertTrue(result["data"]["guided_snapshot_run"]["active"])
        fallback_snapshot.assert_called_once()

    def test_guided_subtitle_run_primes_status_cache_for_follow_up_polling(self):
        owner = _DummyOwner()
        with tempfile.TemporaryDirectory() as tmp:
            media_path = Path(tmp) / "demo.mp4"
            media_path.write_bytes(b"video")

            result = execute_app_command(owner, {"command": "guided-subtitle-run", "path": str(media_path)})

        self.assertTrue(result["ok"])
        cached_entry = app_bridge._peek_status_snapshot_cache(owner, max_age_sec=None)
        self.assertIsNotNone(cached_entry)
        _age, snapshot = cached_entry
        self.assertTrue(snapshot["editor_open"])
        self.assertEqual(snapshot["editor_media_path"], str(media_path))
        self.assertIn("guided_snapshot_run", snapshot)

    def test_dispatch_non_status_command_still_reports_timeout_when_ui_thread_does_not_reply(self):
        owner = _DummyOwner()
        app_thread = object()
        current_thread = object()
        fake_app = SimpleNamespace(thread=lambda: app_thread)

        with patch("ui.main.app_command_bridge.QApplication.instance", return_value=fake_app):
            with patch("ui.main.app_command_bridge.QThread.currentThread", return_value=current_thread):
                result = dispatch_app_command(owner, {"command": "show-home"}, timeout_sec=0.1)

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "command_timeout")

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

    def test_editor_timeline_view_command_exercises_zoom_and_fit(self):
        owner = _DummyOwner()

        zoomed = execute_app_command(owner, {"command": "editor-timeline-view", "options": {"action": "zoom-in"}})
        fitted = execute_app_command(owner, {"command": "editor-timeline-view", "options": {"action": "fit"}})
        windowed = execute_app_command(owner, {"command": "editor-timeline-view", "options": {"action": "time-window"}})

        self.assertTrue(zoomed["ok"])
        self.assertEqual(zoomed["message"], "editor_timeline_view_zoom-in")
        self.assertGreater(zoomed["data"]["timeline_pps"], zoomed["data"]["previous_timeline_pps"])
        self.assertTrue(fitted["ok"])
        self.assertEqual(fitted["message"], "editor_timeline_view_fit")
        self.assertTrue(fitted["data"]["timeline_fit_locked"])
        self.assertEqual(fitted["data"]["editor_runtime"]["timeline_pps"], 8.0)
        self.assertTrue(windowed["ok"])
        self.assertEqual(windowed["message"], "editor_timeline_view_time-window")
        self.assertTrue(windowed["data"]["editor_runtime"]["time_window_applied"])

    def test_editor_subtitle_magnet_command_reports_changed_runtime(self):
        owner = _DummyOwner()

        result = execute_app_command(owner, {"command": "editor-subtitle-magnet"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "editor_subtitle_magnet_done")
        self.assertTrue(result["data"]["changed"])
        self.assertEqual(result["data"]["before_segment_count"], result["data"]["after_segment_count"])

    def test_global_menu_action_save_uses_center_save_button_path(self):
        owner = _DummyOwner()

        result = execute_app_command(owner, {"command": "global-menu-action", "options": {"action": "save"}})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "global_menu_action_center_save")
        self.assertEqual(result["data"]["action_id"], "center_save")
        self.assertEqual(owner.global_menu_bar.actions, ["center_save"])
        self.assertEqual(owner._editor_widget.save_calls, 1)

    def test_global_menu_status_lists_buttons_without_clicking(self):
        owner = _DummyOwner()

        result = execute_app_command(owner, {"command": "global-menu-status"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "global_menu_status")
        action_ids = {item["action_id"] for item in result["data"]["actions"]}
        self.assertIn("center_save", action_ids)
        self.assertIn("right_quit", action_ids)
        self.assertEqual(owner.global_menu_bar.actions, [])

    def test_global_menu_action_rejects_unsafe_action(self):
        owner = _DummyOwner()

        result = execute_app_command(owner, {"command": "global-menu-action", "options": {"action": "right_quit"}})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "global_menu_action_not_allowed")
        self.assertEqual(owner.global_menu_bar.actions, [])

    def test_editor_playback_play_command_marks_center_lock(self):
        owner = _DummyOwner()

        result = execute_app_command(owner, {"command": "editor-playback", "options": {"action": "play"}})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "editor_playback_play")
        self.assertTrue(owner._editor_widget._playing)
        self.assertTrue(result["data"]["editor_runtime"]["playback_center_lock"])

    def test_post_generation_pending_cleanup_keeps_editor_commands_interactive(self):
        owner = _DummyOwner()
        owner._post_generation_gc_scheduled = True
        owner._editor_ai_release_in_progress = True
        owner._editor_ai_runtime_release_requested_for_editor_mode = True
        editor = owner._editor_widget
        editor._subtitle_generation_completed = True
        editor._post_generation_models_release_requested = True
        editor._post_generation_models_released = False
        editor._playhead_sec = 1.5

        status = execute_app_command(owner, {"command": "status"})
        playback = execute_app_command(owner, {"command": "editor-playback", "options": {"action": "play"}})
        split = execute_app_command(owner, {"command": "editor-begin-smart-split", "options": {"line": 1}})
        commit = execute_app_command(owner, {"command": "editor-commit-inline-edit"})
        timeline = execute_app_command(owner, {"command": "editor-timeline-view", "options": {"action": "fit"}})
        save = execute_app_command(owner, {"command": "global-menu-action", "options": {"action": "save"}})

        for result in (status, playback, split, commit, timeline, save):
            self.assertTrue(result["ok"], result)
        self.assertEqual(status["data"]["editor_state"], "ST_IDLE")
        self.assertTrue(playback["data"]["editor_runtime"]["playback_center_lock"])
        self.assertFalse(owner._editor_widget._inline_edit_active)
        self.assertTrue(timeline["data"]["editor_runtime"]["timeline_fit_locked"])
        self.assertEqual(owner._editor_widget.save_calls, 1)
        self.assertTrue(owner._post_generation_gc_scheduled)
        self.assertTrue(owner._editor_ai_release_in_progress)

    def test_editor_video_hide_command_updates_visibility(self):
        owner = _DummyOwner()

        result = execute_app_command(owner, {"command": "editor-video", "options": {"action": "hide"}})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "editor_video_hide")
        self.assertFalse(owner._editor_widget._video_visible)
        self.assertFalse(result["data"]["video_visible"])
        self.assertEqual(result["data"]["editor_runtime"]["active_footer_menu_id"], "")

    def test_editor_stt_mode_command_enables_editor_stt_mode(self):
        owner = _DummyOwner()

        result = execute_app_command(owner, {"command": "editor-stt-mode", "options": {"action": "enable"}})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "editor_stt_mode_updated")
        self.assertTrue(owner._editor_widget._stt_mode_enabled)
        self.assertEqual(result["data"]["state"], "ready_to_listen")

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

    def test_subtitle_time_edit_leaves_editor_controls_interactive(self):
        owner = _DummyOwner()
        editor = owner._editor_widget
        editor._playhead_sec = 0.4

        time_edit = execute_app_command(
            owner,
            {"command": "editor-move-segment-left", "options": {"line": 1}},
        )
        zoom_in = execute_app_command(owner, {"command": "editor-timeline-view", "options": {"action": "zoom-in"}})
        zoom_out = execute_app_command(owner, {"command": "editor-timeline-view", "options": {"action": "zoom-out"}})
        fit = execute_app_command(owner, {"command": "editor-timeline-view", "options": {"action": "fit"}})
        windowed = execute_app_command(owner, {"command": "editor-timeline-view", "options": {"action": "time-window"}})
        magnet = execute_app_command(owner, {"command": "editor-subtitle-magnet"})
        playback = execute_app_command(owner, {"command": "editor-playback", "options": {"action": "play"}})
        footer = execute_app_command(owner, {"command": "editor-video", "options": {"action": "hide"}})
        menu_status = execute_app_command(owner, {"command": "global-menu-status"})
        save = execute_app_command(owner, {"command": "global-menu-action", "options": {"action": "save"}})

        for result in (time_edit, zoom_in, zoom_out, fit, windowed, magnet, playback, footer, menu_status, save):
            self.assertTrue(result["ok"], result)
        self.assertAlmostEqual(editor._segments[1]["start"], 0.4)
        self.assertFalse(editor._inline_edit_active)
        self.assertEqual(zoom_in["message"], "editor_timeline_view_zoom-in")
        self.assertEqual(zoom_out["message"], "editor_timeline_view_zoom-out")
        self.assertTrue(fit["data"]["editor_runtime"]["timeline_fit_locked"])
        self.assertTrue(windowed["data"]["editor_runtime"]["time_window_applied"])
        self.assertTrue(magnet["data"]["changed"])
        self.assertTrue(playback["data"]["editor_runtime"]["playback_center_lock"])
        self.assertEqual(footer["data"]["editor_runtime"]["active_footer_menu_id"], "")
        self.assertIn("center_save", {item["action_id"] for item in menu_status["data"]["actions"]})
        self.assertEqual(owner.global_menu_bar.actions, ["center_save"])
        self.assertEqual(editor.save_calls, 1)

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
        self.assertEqual(result["data"]["selection_source"], "requested")

    def test_editor_begin_smart_split_command_falls_back_to_playhead_segment(self):
        owner = _DummyOwner()
        owner._editor_widget._playhead_sec = 1.5

        result = execute_app_command(
            owner,
            {"command": "editor-begin-smart-split", "options": {"line": 0}},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["line"], 1)
        self.assertEqual(result["data"]["selection_source"], "playhead_fallback")

    def test_editor_begin_smart_split_failure_returns_runtime_snapshot(self):
        owner = _DummyOwner()
        owner._editor_widget._playhead_sec = 0.0

        result = execute_app_command(
            owner,
            {"command": "editor-begin-smart-split", "options": {"line": 0}},
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "smart_split_unavailable")
        self.assertIn("editor_runtime", result["data"])

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

    def test_editor_set_inline_cursor_failure_returns_runtime_snapshot(self):
        owner = _DummyOwner()

        result = execute_app_command(owner, {"command": "editor-set-inline-cursor", "options": {"position": 2}})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "inline_edit_inactive")
        self.assertIn("editor_runtime", result["data"])

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

    def test_open_settings_command_shows_nonmodal_dialog(self):
        owner = _DummyOwner()

        class _FakeSettingsDialog(_DummyVisibleDialog):
            def __init__(self, *_args, **_kwargs):
                super().__init__()
                owner.settings_dialog_opened += 1

        with patch("ui.settings.settings_dialog.SettingsDialog", _FakeSettingsDialog):
            result = execute_app_command(owner, {"command": "open-settings"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "settings_visible")
        self.assertEqual(owner.settings_dialog_opened, 1)
        self.assertIsNotNone(owner._automation_active_dialog)

    def test_open_speaker_settings_command_shows_nonmodal_dialog(self):
        owner = _DummyOwner()

        class _FakeSpeakerDialog(_DummyVisibleDialog):
            def __init__(self, *_args, **_kwargs):
                super().__init__()
                owner.speaker_dialog_opened += 1

        with patch("ui.settings.settings_dialog.SpeakerDialog", _FakeSpeakerDialog):
            result = execute_app_command(owner, {"command": "open-speaker-settings"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "speaker_settings_visible")
        self.assertEqual(owner.speaker_dialog_opened, 1)

    def test_capture_active_dialog_command_saves_dialog_snapshot(self):
        owner = _DummyOwner()
        owner._automation_active_dialog = _DummyVisibleDialog()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "dialog.png"
            result = execute_app_command(owner, {"command": "capture-active-dialog", "path": str(target)})
            self.assertTrue(target.is_file())

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "active_dialog_snapshot_captured")

    def test_close_active_dialog_command_hides_dialog(self):
        owner = _DummyOwner()
        owner._automation_active_dialog = _DummyVisibleDialog()

        result = execute_app_command(owner, {"command": "close-active-dialog"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "active_dialog_closed")
        self.assertIsNone(owner._automation_active_dialog)

    def test_personalization_idle_command_dispatches_requested_action(self):
        owner = _DummyOwner()

        def _fake_start_background(_owner, *, action, runner):
            result = dict(runner() or {})
            return {
                "active": True,
                "active_action": action,
                "last_action": action,
                "last_result": result,
            }

        with patch("ui.main.app_command_bridge._start_background_personalization_action", side_effect=_fake_start_background):
            paused = execute_app_command(owner, {"command": "personalization-idle", "options": {"action": "pause"}})
            resumed = execute_app_command(owner, {"command": "personalization-idle", "options": {"action": "resume"}})
            started = execute_app_command(owner, {"command": "personalization-idle", "options": {"action": "run-now"}})

        self.assertTrue(paused["ok"])
        self.assertTrue(resumed["ok"])
        self.assertTrue(started["ok"])
        self.assertTrue(paused["queued"])
        self.assertTrue(resumed["queued"])
        self.assertTrue(started["queued"])
        self.assertEqual(paused["message"], "personalization_idle_pause_accepted")
        self.assertEqual(resumed["message"], "personalization_idle_resume_accepted")
        self.assertEqual(started["message"], "personalization_idle_run_now_accepted")
        self.assertEqual(owner.personalization_actions, ["pause", "resume", "run-now"])

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
