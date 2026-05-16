# Version: 01.00.00
# Phase: PHASE2
from __future__ import annotations

import threading

from PyQt6.QtCore import QTimer

from core.runtime import config
from core.runtime.logger import get_logger
from ui.editor.editor_pipeline_safety import EditorPipelineSafetyMixin


class EditorPipelineSignalBridgeMixin(EditorPipelineSafetyMixin):
    def _reconnect_signal(self, signal, slot) -> bool:
        if signal is None or not hasattr(signal, "connect") or slot is None:
            return False
        try:
            signal.disconnect(slot)
        except (RuntimeError, TypeError):
            pass
        try:
            signal.connect(slot)
            return True
        except (RuntimeError, TypeError):
            return False

    def _is_video_playing_for_timeline_fit(self) -> bool:
        try:
            player = getattr(getattr(self, "video_player", None), "media_player", None)
            return bool(player and player.playbackState() == player.PlaybackState.PlayingState)
        except Exception:
            return False

    def _auto_fit_timeline_if_user_view_allows(self, timeline) -> bool:
        if timeline is None or self._is_video_playing_for_timeline_fit():
            return False
        auto_fit = getattr(timeline, "auto_fit_to_view", None)
        if callable(auto_fit):
            try:
                return bool(auto_fit())
            except Exception:
                return False
        if bool(getattr(timeline, "_manual_zoom_since_fit", False)):
            return False
        try:
            timeline.fit_to_view()
            return True
        except Exception:
            return False

    def _hook_backend_signals(self):
        main_w = self._pipeline_window()
        self._pipeline_call_if_callable(
            self,
            "_connect_cut_boundary_placeholder_signal",
            label="컷 경계 placeholder signal 연결",
            log=False,
        )
        if hasattr(main_w, "backend") and main_w.backend:
            self._reconnect_signal(getattr(main_w.backend, "sig_chunk_done", None), self.append_segments)
            self._reconnect_signal(getattr(main_w.backend, "sig_progress", None), self.update_progress)
            if getattr(self, "is_batch_mode", False) and hasattr(main_w.backend, "sig_batch_finished"):
                self._reconnect_signal(getattr(main_w.backend, "sig_batch_finished", None), self._on_batch_finished)

    def _on_batch_finished(self):
        self.sm.set_custom_status("✅ 배치 작업이 모두 완료되었습니다.")
        self._send_ntfy_batch_complete()

    def _send_ntfy_batch_complete(self):
        main_w = self._pipeline_window()
        if not getattr(main_w, "_is_auto_pipeline", False):
            return
        try:
            from core.notifier import send_ntfy
        except Exception as exc:
            self._pipeline_log_nonfatal("배치 완료 알림 로더", exc)
            return

        self._pipeline_best_effort(
            lambda: send_ntfy(
                title=f"🎉 {config.APP_NAME} 알림",
                message="🎬 모든 파일의 자막 생성이 완료되었습니다!",
                tags="tada,sparkles,clapper",
            ),
            label="배치 완료 알림 발송",
            log=False,
        )

    def _connect_cut_boundary_placeholder_signal(self):
        """Connect cut-boundary placeholder refresh signal to editor UI bridge."""
        main_w = self._pipeline_window()
        if main_w is None:
            return

        connected = False
        for owner in (main_w, self):
            try:
                sig = getattr(owner, "_sig_refresh_cut_boundary_placeholder", None)
                if sig is None:
                    continue
                connected = self._reconnect_signal(
                    sig,
                    self._refresh_cut_boundary_placeholder_from_project,
                ) or connected
            except Exception as exc:
                self._pipeline_log_nonfatal("컷 경계 placeholder signal 연결", exc)

        if connected:
            self._pipeline_best_effort(
                lambda: QTimer.singleShot(0, self._refresh_cut_boundary_placeholder_from_project),
                label="컷 경계 placeholder 초기 refresh 예약",
                log=False,
            )

    def _apply_cut_boundary_topicless_rows_to_ui(self, rows, *, source: str = "stream"):
        """Push live cut-boundary middle split rows into timeline/canvas immediately."""
        try:
            if threading.current_thread() is not threading.main_thread():
                snapshot = [dict(row) for row in list(rows or []) if isinstance(row, dict)]
                QTimer.singleShot(0, lambda rows=snapshot: self._apply_cut_boundary_topicless_rows_to_ui(rows, source=source))
                return
        except Exception:
            pass

        rows = [dict(row) for row in list(rows or []) if isinstance(row, dict)]
        try:
            main_w = self.window()
        except Exception:
            main_w = None

        result_dict = None
        if rows:
            result_dict = {
                "segments": list(rows),
                "chapters": [],
                "edit_decisions": [],
                "edl_segments": [],
                "guide_markdown": "",
                "schema_version": "roughcut_result.v2",
                "draft_state": {"status": "review"},
                "video_summary": f"컷 경계 기반 주제없음 중분류 {len(rows)}개",
                "source": f"cut_boundary_{source}",
            }

        row_attrs = (
            "_cut_boundary_topicless_middle_segments",
            "_roughcut_segments",
            "roughcut_segments",
            "_middle_segments",
            "middle_segments",
            "_chapter_segments",
            "chapter_segments",
            "_roughcut_draft_segments",
        )
        result_attrs = ("_roughcut_result", "roughcut_result", "_roughcut_draft_result")

        timeline = getattr(self, "timeline", None)
        canvas = getattr(timeline, "canvas", None) if timeline is not None else None
        global_canvas = getattr(timeline, "global_canvas", None) if timeline is not None else None

        for obj in (self, main_w, timeline, canvas, global_canvas):
            if obj is None:
                continue
            for attr in row_attrs:
                try:
                    setattr(obj, attr, list(rows))
                except Exception:
                    pass
            for attr in result_attrs:
                try:
                    setattr(obj, attr, dict(result_dict) if isinstance(result_dict, dict) else None)
                except Exception:
                    pass
            try:
                invalidator = getattr(obj, "_invalidate_marker_caches", None)
                if callable(invalidator):
                    invalidator()
                static_invalidator = getattr(obj, "_invalidate_static_cache", None)
                if callable(static_invalidator):
                    static_invalidator()
                if hasattr(obj, "_roughcut_major_cache_key"):
                    obj._roughcut_major_cache_key = None
                    obj._roughcut_major_cache = []
                if hasattr(obj, "_analysis_markers_cache_key"):
                    obj._analysis_markers_cache_key = None
                if hasattr(obj, "_visible_analysis_markers_cache_key"):
                    obj._visible_analysis_markers_cache_key = None
                if hasattr(obj, "_paint_index_cache"):
                    obj._paint_index_cache.pop("roughcut_major_markers", None)
                if hasattr(obj, "_render_epoch"):
                    obj._render_epoch = int(getattr(obj, "_render_epoch", 0) or 0) + 1
            except Exception:
                pass
            try:
                obj.update()
            except Exception:
                pass

        for name in ("_sync_roughcut_segments_to_timeline", "_sync_roughcut_to_timeline", "_redraw_timeline"):
            fn = getattr(self, name, None)
            if not callable(fn):
                continue
            try:
                fn()
                break
            except TypeError:
                try:
                    fn(rows)
                    break
                except Exception:
                    pass
            except Exception:
                pass

        try:
            if timeline is not None:
                timeline.update()
        except Exception:
            pass

    def _refresh_cut_boundary_placeholder_from_project(self):
        """Load gray topicless middle segments from project and push them to UI objects.

        This must run on the Qt/main thread. Backend cut scanning only saves
        project data and emits a lightweight refresh signal.
        """
        try:
            if threading.current_thread() is not threading.main_thread():
                QTimer.singleShot(0, self._refresh_cut_boundary_placeholder_from_project)
                return
        except Exception:
            pass

        try:
            main_w = self.window()
        except Exception:
            main_w = None

        try:
            project_path = ""
            if main_w is not None:
                project_path = str(getattr(main_w, "_current_project_path", "") or "")
            if not project_path:
                project_path = str(getattr(self, "_current_project_path", "") or "")
            if not project_path:
                return

            from core.project.project_io import read_project_file
            from core.roughcut.cut_boundary_placeholder import (
                extract_topicless_placeholders_from_project,
                rows_are_placeholder_only,
            )

            project = read_project_file(project_path)
            analysis = project.get("analysis", {}) if isinstance(project.get("analysis"), dict) else {}
            reviewed_rows = [
                dict(row)
                for row in list(analysis.get("cut_boundary_reviewed_rows") or [])
                if isinstance(row, dict)
            ]
            preliminary_rows = [
                dict(row)
                for row in list(
                    analysis.get("preliminary_middle_segments")
                    or project.get("preliminary_middle_segments")
                    or []
                )
                if isinstance(row, dict)
            ]
            middle_rows = [
                dict(row)
                for row in list(
                    analysis.get("middle_segments")
                    or project.get("middle_segments")
                    or []
                )
                if isinstance(row, dict)
            ]
            provisional_rows = [
                dict(row)
                for row in list(analysis.get("cut_boundary_provisional_boundaries") or [])
                if isinstance(row, dict)
            ]
            placeholder_rows = [dict(row) for row in list(extract_topicless_placeholders_from_project(project_path) or [])]
            rows = list(middle_rows or placeholder_rows)

            if not provisional_rows:
                try:
                    if hasattr(self, "_set_auto_cut_boundary_scan_active"):
                        self._set_auto_cut_boundary_scan_active(False)
                except Exception:
                    pass
                try:
                    if hasattr(self, "_set_auto_cut_boundary_scan_lines"):
                        self._set_auto_cut_boundary_scan_lines([])
                except Exception:
                    pass

            for attr in (
                "_cut_boundary_topicless_middle_segments",
                "_roughcut_segments",
                "roughcut_segments",
                "_middle_segments",
                "middle_segments",
                "_chapter_segments",
                "chapter_segments",
                "_roughcut_draft_segments",
            ):
                try:
                    setattr(self, attr, list(rows))
                except Exception:
                    pass
            try:
                self._cut_boundary_topicless_middle_segments = list(placeholder_rows)
            except Exception:
                pass
            try:
                self._cut_boundary_reviewed_rows = list(reviewed_rows)
            except Exception:
                pass
            for attr in ("_preliminary_middle_segments", "preliminary_middle_segments"):
                try:
                    setattr(self, attr, list(preliminary_rows))
                except Exception:
                    pass

            result_dict = None
            stored_result = analysis.get("roughcut_result")
            if isinstance(stored_result, dict):
                result_dict = dict(stored_result)
            elif isinstance(project.get("roughcut_result"), dict):
                result_dict = dict(project.get("roughcut_result"))
            elif rows:
                placeholder_only = rows_are_placeholder_only(rows)
                review_required = any(
                    bool(row.get("needs_review"))
                    or str(row.get("status") or "provisional") != "confirmed"
                    for row in rows
                )
                result_dict = {
                    "segments": list(rows),
                    "chapters": [],
                    "edit_decisions": [],
                    "edl_segments": [],
                    "guide_markdown": "",
                    "schema_version": "roughcut_result.v2",
                    "draft_state": {"status": "review" if review_required else "confirmed"},
                    "video_summary": (
                        f"컷 경계 기반 주제없음 중분류 {len(rows)}개"
                        if placeholder_only
                        else f"프로젝트 중분류 {len(rows)}개"
                    ),
                }
            for attr in ("_roughcut_result", "roughcut_result", "_roughcut_draft_result"):
                try:
                    setattr(self, attr, dict(result_dict) if isinstance(result_dict, dict) else None)
                except Exception:
                    pass

            timeline = getattr(self, "timeline", None)
            canvas = getattr(timeline, "canvas", None) if timeline is not None else None
            global_canvas = getattr(timeline, "global_canvas", None) if timeline is not None else None

            for obj in (timeline, canvas, global_canvas):
                if obj is None:
                    continue
                try:
                    setattr(obj, "_cut_boundary_reviewed_rows", list(reviewed_rows))
                except Exception:
                    pass
                for attr in ("_preliminary_middle_segments", "preliminary_middle_segments"):
                    try:
                        setattr(obj, attr, list(preliminary_rows))
                    except Exception:
                        pass
                for attr in (
                    "_cut_boundary_topicless_middle_segments",
                    "_roughcut_segments",
                    "roughcut_segments",
                    "_middle_segments",
                    "middle_segments",
                    "_chapter_segments",
                    "chapter_segments",
                    "_roughcut_draft_segments",
                ):
                    try:
                        setattr(obj, attr, list(rows))
                    except Exception:
                        pass
                try:
                    setattr(obj, "_cut_boundary_topicless_middle_segments", list(placeholder_rows))
                except Exception:
                    pass
                try:
                    invalidator = getattr(obj, "_invalidate_marker_caches", None)
                    if callable(invalidator):
                        invalidator()
                    static_invalidator = getattr(obj, "_invalidate_static_cache", None)
                    if callable(static_invalidator):
                        static_invalidator()
                    if hasattr(obj, "_roughcut_major_cache_key"):
                        obj._roughcut_major_cache_key = None
                        obj._roughcut_major_cache = []
                    if hasattr(obj, "_analysis_markers_cache_key"):
                        obj._analysis_markers_cache_key = None
                    if hasattr(obj, "_visible_analysis_markers_cache_key"):
                        obj._visible_analysis_markers_cache_key = None
                    if hasattr(obj, "_paint_index_cache"):
                        obj._paint_index_cache.pop("roughcut_major_markers", None)
                    if hasattr(obj, "_render_epoch"):
                        obj._render_epoch = int(getattr(obj, "_render_epoch", 0) or 0) + 1
                except Exception:
                    pass
                try:
                    obj.update()
                except Exception:
                    pass

            refresh_names = (
                "_refresh_roughcut_panel",
                "_refresh_roughcut_view",
                "_reload_roughcut_view",
                "_load_roughcut_from_project",
                "_sync_roughcut_segments_to_timeline",
                "_sync_roughcut_to_timeline",
                "_redraw_timeline",
            )

            for owner in (self, main_w):
                if owner is None:
                    continue
                try:
                    setattr(owner, "_cut_boundary_reviewed_rows", list(reviewed_rows))
                except Exception:
                    pass
                for attr in (
                    "_cut_boundary_topicless_middle_segments",
                    "_roughcut_segments",
                    "roughcut_segments",
                    "_middle_segments",
                    "middle_segments",
                    "_chapter_segments",
                    "chapter_segments",
                    "_roughcut_draft_segments",
                ):
                    try:
                        setattr(owner, attr, list(rows))
                    except Exception:
                        pass
                try:
                    setattr(owner, "_cut_boundary_topicless_middle_segments", list(placeholder_rows))
                except Exception:
                    pass
                for attr in ("_preliminary_middle_segments", "preliminary_middle_segments"):
                    try:
                        setattr(owner, attr, list(preliminary_rows))
                    except Exception:
                        pass
                for attr in ("_roughcut_result", "roughcut_result", "_roughcut_draft_result"):
                    try:
                        setattr(owner, attr, dict(result_dict) if isinstance(result_dict, dict) else None)
                    except Exception:
                        pass
                for name in refresh_names:
                    fn = getattr(owner, name, None)
                    if not callable(fn):
                        continue
                    try:
                        fn()
                    except TypeError:
                        try:
                            fn(rows)
                        except Exception:
                            pass
                    except Exception:
                        pass

            self._auto_fit_timeline_if_user_view_allows(timeline)

        except Exception as exc:
            try:
                get_logger().log(f"  ⚠️ [컷 경계] UI 회색 중분류 반영 실패: {exc}")
            except Exception:
                pass
