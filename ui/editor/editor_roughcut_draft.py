# Version: 03.13.05
# Phase: PHASE2
"""Post-generation roughcut draft helpers for the subtitle editor."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import replace

from PyQt6.QtCore import QTimer

from core.runtime.logger import get_logger
from ui.project.project_session_runtime import attach_project_session
from ui.queue.queue_dispatch import dispatch_queue_status, find_queue_row_for_media, sync_saved_queue_state


class EditorRoughcutDraftMixin:
    def _cancel_post_generation_roughcut_draft(self, *, reason: str = "") -> bool:
        timer = getattr(self, "_roughcut_draft_timer", None)
        try:
            timer_active = bool(timer is not None and timer.isActive())
        except Exception:
            timer_active = False
        pending = bool(getattr(self, "_roughcut_draft_pending", False))
        status = str(getattr(self, "_roughcut_draft_status", "") or "")
        thread = getattr(self, "_roughcut_draft_thread", None)
        try:
            thread_alive = bool(thread is not None and thread.is_alive())
        except Exception:
            thread_alive = False
        if thread_alive:
            return False
        reason_text = str(reason or "").strip()
        if reason_text == "편집 시작" and status in {"running", "saving", "done"}:
            # 러프컷 hot path: 적용/완료 중 내부 UI 갱신은 사용자 취소가 아니므로 오해되는 취소 로그를 남기지 않는다.
            if status == "done":
                if timer is not None and timer_active:
                    try:
                        timer.stop()
                    except Exception:
                        timer_active = False
                self._roughcut_draft_pending = False
            return False
        try:
            current_auto_epoch = int(getattr(self, "_roughcut_draft_auto_schedule_epoch", 0) or 0)
        except Exception:
            current_auto_epoch = 0
        if not (timer_active or pending or status == "queued"):
            if reason_text == "수동 저장" and current_auto_epoch > 0:
                self._roughcut_draft_auto_schedule_blocked_epoch = current_auto_epoch
                self._roughcut_draft_cancelled = True
            return False
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass
        self._roughcut_draft_pending = False
        self._roughcut_draft_cancelled = True
        self._roughcut_draft_auto_schedule_blocked_epoch = current_auto_epoch
        self._roughcut_draft_generation = int(getattr(self, "_roughcut_draft_generation", 0) or 0) + 1
        self._set_roughcut_draft_status("idle")
        mark_done = getattr(self, "_mark_roughcut_queue_done", None)
        if callable(mark_done):
            try:
                mark_done()
            except Exception:
                pass
        detail = f": {reason}" if reason_text else ""
        get_logger().log(f"⏹️ 러프컷 자동 실행 취소{detail}")
        return True

    def _cut_boundary_runtime_settled_for_roughcut(self) -> bool:
        if bool(getattr(self, "_auto_cut_boundary_scan_active", False)):
            return False
        try:
            main_w = self.window()
        except Exception:
            main_w = None
        for backend in (
            getattr(main_w, "backend", None),
            getattr(main_w, "backend_fast", None),
        ):
            if backend is None:
                continue
            try:
                prescan = getattr(backend, "_cut_boundary_prescan_thread", None)
                follower = getattr(backend, "_cut_boundary_follower_thread", None)
                if (prescan is not None and prescan.is_alive()) or (follower is not None and follower.is_alive()):
                    return False
            except Exception:
                continue
        runtime_rows = [
            dict(row)
            for row in list(getattr(self, "_auto_cut_boundary_scan_lines", []) or [])
            if isinstance(row, dict)
            and str(row.get("reason", "") or "") != "manual_roughcut_middle_right_click"
        ]
        if runtime_rows:
            return False
        try:
            project_path = str(getattr(main_w, "_current_project_path", "") or "")
        except Exception:
            project_path = ""
        if not project_path or not os.path.exists(project_path):
            return True
        try:
            from core.project.project_io import read_project_file

            project = read_project_file(project_path)
            analysis = project.get("analysis", {}) if isinstance(project.get("analysis"), dict) else {}
            provisional_rows = list(analysis.get("cut_boundary_provisional_boundaries") or [])
            return not bool(provisional_rows)
        except Exception:
            return True

    def _draft_reference_major_segments(self) -> list[dict]:
        try:
            window_owner = self.window()
        except Exception:
            window_owner = None
        preferred_rows = []
        fallback_rows = []
        for owner in (self, window_owner):
            if owner is None:
                continue
            for attr in (
                "_cut_boundary_topicless_middle_segments",
                "cut_boundary_topicless_middle_segments",
            ):
                raw = getattr(owner, attr, None)
                if isinstance(raw, list) and raw:
                    preferred_rows = [dict(row) for row in raw if isinstance(row, dict)]
                    if preferred_rows:
                        return preferred_rows
            for attr in (
                "_middle_segments",
                "middle_segments",
                "_roughcut_segments",
                "roughcut_segments",
            ):
                raw = getattr(owner, attr, None)
                if isinstance(raw, list) and raw:
                    fallback_rows = [dict(row) for row in raw if isinstance(row, dict)]
                    if fallback_rows:
                        break
        try:
            main_w = self.window()
            project_path = str(getattr(main_w, "_current_project_path", "") or "")
        except Exception:
            project_path = ""
        if not project_path:
            return []
        try:
            from core.project.project_io import read_project_file

            project = read_project_file(project_path)
            analysis = project.get("analysis", {}) if isinstance(project.get("analysis"), dict) else {}
            for key in (
                "cut_boundary_topicless_middle_segments",
                "topicless_middle_segments",
                "roughcut_topicless_segments",
            ):
                rows = analysis.get(key, [])
                if isinstance(rows, list) and rows:
                    return [dict(row) for row in rows if isinstance(row, dict)]
            rows = analysis.get("middle_segments", [])
            if isinstance(rows, list) and rows:
                return [dict(row) for row in rows if isinstance(row, dict)]
            rows = project.get("middle_segments", [])
            if isinstance(rows, list) and rows:
                return [dict(row) for row in rows if isinstance(row, dict)]
        except Exception:
            pass
        if fallback_rows:
            return fallback_rows
        return []

    def _draft_reviewed_cut_boundaries(self) -> list[dict]:
        try:
            window_owner = self.window()
        except Exception:
            window_owner = None
        for owner in (self, window_owner):
            if owner is None:
                continue
            for attr in (
                "_cut_boundary_reviewed_rows",
                "cut_boundary_reviewed_rows",
            ):
                raw = getattr(owner, attr, None)
                if isinstance(raw, list) and raw:
                    rows = [dict(row) for row in raw if isinstance(row, dict)]
                    if rows:
                        return rows
        try:
            main_w = self.window()
            project_path = str(getattr(main_w, "_current_project_path", "") or "")
        except Exception:
            project_path = ""
        if not project_path or not os.path.exists(project_path):
            return [dict(row) for row in list(getattr(self, "_auto_cut_boundary_scan_lines", []) or []) if isinstance(row, dict)]
        try:
            from core.project.project_io import read_project_file

            project = read_project_file(project_path)
            analysis = project.get("analysis", {}) if isinstance(project.get("analysis"), dict) else {}
            rows = list(
                analysis.get("cut_boundary_reviewed_rows")
                or analysis.get("cut_boundaries")
                or analysis.get("cut_boundary_provisional_boundaries")
                or []
            )
            return [dict(row) for row in rows if isinstance(row, dict)]
        except Exception:
            rows = list(getattr(self, "_cut_boundary_provisional_rows", []) or [])
            if not rows:
                rows = list(getattr(self, "_auto_cut_boundary_scan_lines", []) or [])
            return [dict(row) for row in rows if isinstance(row, dict)]

    def _apply_roughcut_middle_segments_to_ui(self, rows: list[dict], result) -> None:
        rows = [dict(row) for row in list(rows or []) if isinstance(row, dict)]
        preliminary_rows = [
            dict(row)
            for row in list(getattr(self, "_pending_preliminary_middle_segments", []) or [])
            if isinstance(row, dict)
        ]
        try:
            main_w = self.window()
        except Exception:
            main_w = None
        timeline = getattr(self, "timeline", None)
        canvas = getattr(timeline, "canvas", None) if timeline is not None else None
        global_canvas = getattr(timeline, "global_canvas", None) if timeline is not None else None
        row_attrs = (
            "_middle_segments",
            "middle_segments",
            "_roughcut_segments",
            "roughcut_segments",
            "_chapter_segments",
            "chapter_segments",
            "_roughcut_draft_segments",
        )
        result_attrs = ("_roughcut_result", "roughcut_result", "_roughcut_draft_result")
        for obj in (self, main_w, timeline, canvas, global_canvas):
            if obj is None:
                continue
            for attr in ("_preliminary_middle_segments", "preliminary_middle_segments"):
                try:
                    setattr(obj, attr, list(preliminary_rows))
                except Exception:
                    pass
            for attr in row_attrs:
                try:
                    setattr(obj, attr, list(rows))
                except Exception:
                    pass
            for attr in result_attrs:
                try:
                    setattr(obj, attr, result)
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

    def _sorted_roughcut_middle_rows(self, rows: list[dict] | tuple | None) -> list[dict]:
        def _num(value, default: float = 0.0) -> float:
            try:
                return float(value)
            except Exception:
                return default

        cleaned = [dict(row) for row in list(rows or []) if isinstance(row, dict)]
        return sorted(
            cleaned,
            key=lambda row: (
                _num(row.get("start", 0.0)),
                _num(row.get("end", 0.0)),
                str(row.get("major_id") or row.get("segment_id") or row.get("id") or ""),
            ),
        )

    def _sorted_roughcut_result(self, result):
        try:
            original_segments = tuple(getattr(result, "segments", ()) or ())
            segments = tuple(
                sorted(
                    original_segments,
                    key=lambda seg: (
                        float(getattr(seg, "start", 0.0) or 0.0),
                        float(getattr(seg, "end", 0.0) or 0.0),
                        str(getattr(seg, "segment_id", "") or ""),
                    ),
                )
            )
            if segments == original_segments:
                return result
            return replace(result, segments=segments)
        except Exception:
            return result

    def _roughcut_thread_alive(self) -> bool:
        thread = getattr(self, "_roughcut_draft_thread", None)
        try:
            return bool(thread is not None and thread.is_alive())
        except Exception:
            return False

    def _save_current_subtitles_for_manual_roughcut(self) -> bool:
        save = getattr(self, "_on_save", None)
        if not callable(save):
            return True
        try:
            return bool(
                save(
                    skip_auto_next=True,
                    write_backup=True,
                    schedule_analysis_refresh=False,
                    queue_learning=False,
                    allow_project_create=True,
                    auto_export=False,
                )
            )
        except TypeError:
            return bool(save())
        except Exception as exc:
            get_logger().log(f"⚠️ 러프컷 LLM 수동 실행 전 자막 저장 실패: {exc}")
            return False

    def _run_manual_roughcut_llm_from_global_canvas(self) -> None:
        if self._roughcut_thread_alive():
            get_logger().log("⏳ 러프컷 LLM 수동 실행 생략: 이미 러프컷 LLM이 실행 중입니다.")
            self._mark_roughcut_queue_active("⏳ [러프컷 LLM] 이미 실행 중")
            return
        get_logger().log("💾 러프컷 LLM 수동 실행: 현재 자막을 먼저 저장합니다.")
        if not self._save_current_subtitles_for_manual_roughcut():
            self._set_roughcut_draft_status("failed")
            self._mark_roughcut_queue_done(note="자막 저장 실패")
            return
        cancel_roughcut = getattr(self, "_cancel_post_generation_roughcut_draft", None)
        if callable(cancel_roughcut):
            try:
                cancel_roughcut(reason="러프컷 LLM 수동 실행")
            except Exception:
                pass
        self._roughcut_draft_manual_run_requested = True
        self._roughcut_llm_cooldown_until = 0.0
        self._schedule_post_generation_roughcut_draft(
            force=True,
            require_autorun=False,
            settings_override={
                "roughcut_llm_enabled": True,
                "roughcut_run_after_subtitle_generation": True,
            },
        )

    def _post_generation_local_llm_release_requested(self, settings: dict, segments: list[dict]) -> bool:
        if bool(getattr(self, "_roughcut_draft_manual_run_requested", False)):
            return False
        if not bool(getattr(self, "_post_generation_models_release_requested", False)) and not bool(
            getattr(self, "_post_generation_models_released", False)
        ):
            try:
                main_w = self.window()
                if not bool(getattr(main_w, "_editor_ai_runtime_release_requested_for_editor_mode", False)):
                    return False
            except Exception:
                return False
        try:
            from core.llm.openai_provider import is_openai_model
            from core.roughcut.roughcut_llm_config import resolve_roughcut_llm_config

            llm_config = resolve_roughcut_llm_config(settings, subtitle_rows=list(segments or []))
            provider = str(llm_config.provider or "").strip().lower()
            model = str(llm_config.model or "").strip()
            if not llm_config.enabled or not model or "사용 안함" in model or provider == "none":
                return False
            if provider in {"openai", "google", "gemini"} or is_openai_model(model) or "gemini" in model.lower():
                return False
            return True
        except Exception:
            provider = str(settings.get("selected_llm_provider") or settings.get("roughcut_llm_provider") or "ollama")
            return provider.strip().lower() not in {"openai", "google", "gemini", "none"}

    def _schedule_post_roughcut_model_release(self):
        if bool(getattr(self, "_post_generation_models_release_requested", False)) or bool(
            getattr(self, "_post_generation_models_released", False)
        ):
            return
        release = getattr(self, "_release_ai_models_after_roughcut_draft", None)
        if callable(release):
            try:
                QTimer.singleShot(0, release)
                return
            except RuntimeError:
                return
            except Exception:
                pass
        try:
            main_w = self.window()
        except RuntimeError:
            return
        except Exception:
            return
        release = getattr(main_w, "_release_ai_models_for_editor_mode", None)
        if callable(release):
            try:
                QTimer.singleShot(0, lambda: release(force=True, preserve_roughcut_status=True))
            except RuntimeError:
                return
            except Exception:
                pass

    def _draft_settings_snapshot(self) -> dict:
        settings = dict(getattr(self, "settings", {}) or {})
        try:
            from core.settings import load_settings

            settings.update(load_settings())
        except Exception:
            pass
        override = getattr(self, "_roughcut_draft_settings_override", None)
        if isinstance(override, dict):
            settings.update(override)
        return settings

    def _roughcut_draft_runtime_enabled(self) -> bool:
        if bool(getattr(self, "_roughcut_draft_manual_run_requested", False)):
            return True
        try:
            from core.roughcut import editor_roughcut_draft_enabled

            return editor_roughcut_draft_enabled(self._draft_settings_snapshot())
        except Exception:
            return False

    def _roughcut_draft_post_generation_autorun_enabled(self) -> bool:
        settings = self._draft_settings_snapshot()
        try:
            from core.roughcut.editor_draft import editor_roughcut_draft_autorun_enabled

            return bool(editor_roughcut_draft_autorun_enabled(settings))
        except Exception:
            value = settings.get("roughcut_run_after_subtitle_generation", None)
            if isinstance(value, str):
                enabled = value.strip().lower() not in {"0", "false", "off", "no", "사용 안함", "끔"}
            elif value is None:
                enabled = None
            else:
                enabled = bool(value)
            llm_enabled = bool(settings.get("roughcut_llm_enabled", False))
            if not llm_enabled:
                return False
            if enabled is True:
                return True
            if self._roughcut_draft_runtime_enabled():
                return True
            return bool(enabled)

    def _roughcut_playback_active(self) -> bool:
        try:
            player = getattr(getattr(self, "video_player", None), "media_player", None)
            return bool(player and player.playbackState() == player.PlaybackState.PlayingState)
        except Exception:
            return False

    def _set_roughcut_draft_status(self, status: str, count: int | None = None):
        self._roughcut_draft_status = str(status or "idle")
        if count is not None:
            self._last_roughcut_draft_major_count = int(count)
        if threading.current_thread() is not threading.main_thread():
            return
        try:
            main_w = self.window()
            if hasattr(main_w, "_refresh_saved_status_label"):
                main_w._refresh_saved_status_label()
        except Exception:
            pass

    def _ensure_post_generation_editor_interactive(self) -> None:
        try:
            self._is_ai_processing = False
        except Exception:
            pass
        try:
            state_manager = getattr(self, "sm", None)
            if state_manager is not None and (
                bool(getattr(state_manager, "is_locked", False))
                or str(getattr(state_manager, "state", "") or "") == "ST_PROC"
            ):
                state_manager.complete_ai()
        except Exception:
            pass
        timeline = getattr(self, "timeline", None)
        canvas = getattr(timeline, "canvas", None) if timeline is not None else None
        if canvas is not None:
            try:
                canvas._editor_processing_input_locked = False
                canvas.setProperty("editor_processing_input_locked", False)
            except Exception:
                pass
        if timeline is not None:
            for method_name, arg in (
                ("set_playhead_busy", False),
                ("set_playback_center_lock", False),
            ):
                method = getattr(timeline, method_name, None)
                if callable(method):
                    try:
                        method(arg)
                    except Exception:
                        pass
        try:
            main_w = self.window()
            setattr(main_w, "_auto_processing_active", False)
        except Exception:
            pass

    def _roughcut_queue_row(self) -> int | None:
        try:
            main_w = self.window()
        except Exception:
            return None
        if main_w is None:
            return None
        current_row_hint = None
        current_row_getter = getattr(main_w, "queue_active_row_index", None)
        if callable(current_row_getter):
            try:
                current_row_hint = int(current_row_getter())
            except Exception:
                current_row_hint = None
        return find_queue_row_for_media(
            main_w,
            media_path=getattr(self, "media_path", ""),
            current_row_hint=current_row_hint,
        )

    def _ensure_roughcut_queue_row(self) -> int | None:
        row = self._roughcut_queue_row()
        if row is not None:
            return row
        try:
            main_w = self.window()
        except Exception:
            return None
        if main_w is None:
            return None
        media_path = str(getattr(self, "media_path", "") or "")
        if not media_path:
            return None
        row_count_getter = getattr(main_w, "queue_row_count", None)
        row_count = 0
        if callable(row_count_getter):
            try:
                row_count = max(0, int(row_count_getter() or 0))
            except Exception:
                row_count = 0
        if row_count > 0:
            return None
        initializer = getattr(main_w, "init_queue_list", None)
        if not callable(initializer):
            return None
        try:
            initializer([media_path])
        except Exception:
            return None
        return self._roughcut_queue_row()

    def _roughcut_queue_expected_text(
        self,
        row: int | None = None,
        *,
        fallback_seconds: float | None = None,
    ) -> str:
        if row is None:
            row = self._ensure_roughcut_queue_row()
        if row is None:
            if fallback_seconds and fallback_seconds > 0.0:
                return str(max(1, int(round(float(fallback_seconds)))))
            return ""
        try:
            main_w = self.window()
        except Exception:
            main_w = None
        expected_getter = getattr(main_w, "queue_row_expected_seconds", None) if main_w is not None else None
        expected_seconds = 0.0
        if callable(expected_getter):
            try:
                expected_seconds = float(expected_getter(int(row)) or 0.0)
            except Exception:
                expected_seconds = 0.0
        if expected_seconds <= 0.0:
            if fallback_seconds and fallback_seconds > 0.0:
                return str(max(1, int(round(float(fallback_seconds)))))
            return ""
        metrics_getter = getattr(main_w, "queue_row_metrics", None) if main_w is not None else None
        if not callable(metrics_getter):
            return str(max(1, int(round(expected_seconds))))
        try:
            metrics = dict(metrics_getter(int(row)) or {})
        except Exception:
            return str(max(1, int(round(expected_seconds))))
        return str(metrics.get("expected_label", "") or "")

    def _mark_roughcut_queue_active(self, status_text: str, *, expected_seconds: float | None = None) -> None:
        row = self._ensure_roughcut_queue_row()
        if row is None:
            return
        try:
            main_w = self.window()
        except Exception:
            return
        dispatch_queue_status(
            main_w,
            row,
            status_text,
            self._roughcut_queue_expected_text(row, fallback_seconds=expected_seconds),
        )

    def _mark_roughcut_queue_done(self, *, note: str = "") -> None:
        row = self._ensure_roughcut_queue_row()
        if row is None:
            return
        try:
            main_w = self.window()
        except Exception:
            return
        if note:
            dispatch_queue_status(
                main_w,
                row,
                f"✅ 완료 · {note}",
                self._roughcut_queue_expected_text(row),
            )
            return
        sync_saved_queue_state(
            main_w,
            media_path=getattr(self, "media_path", ""),
            current_row_hint=row,
        )

    def _schedule_post_generation_roughcut_draft(
        self,
        force: bool = False,
        *,
        require_autorun: bool = True,
        settings_override: dict | None = None,
    ):
        manual_run = bool(getattr(self, "_roughcut_draft_manual_run_requested", False))
        try:
            current_epoch = int(getattr(self, "_roughcut_draft_auto_schedule_epoch", 0) or 0)
            blocked_epoch = int(getattr(self, "_roughcut_draft_auto_schedule_blocked_epoch", 0) or 0)
        except Exception:
            current_epoch = 0
            blocked_epoch = 0
        if not manual_run and current_epoch > 0 and blocked_epoch == current_epoch:
            # 수동 저장이 취소한 생성완료 singleShot 예약이 뒤늦게 와도 러프컷 LLM을 부활시키지 않는다.
            self._roughcut_draft_pending = False
            self._set_roughcut_draft_status("idle")
            if isinstance(settings_override, dict):
                self._roughcut_draft_settings_override = None
            get_logger().log("⏭️ 러프컷 자동 실행 생략: 수동 저장으로 취소된 예약입니다.")
            return
        self._roughcut_draft_cancelled = False
        if isinstance(settings_override, dict):
            self._roughcut_draft_settings_override = dict(settings_override)
        if force and require_autorun and not self._roughcut_draft_post_generation_autorun_enabled():
            self._roughcut_draft_pending = False
            self._set_roughcut_draft_status("disabled")
            if isinstance(settings_override, dict):
                self._roughcut_draft_settings_override = None
            get_logger().log("⏭️ 러프컷 자동 실행 생략: 생성 완료 후 자동 실행 설정이 꺼져 있습니다.")
            return
        if not self._roughcut_draft_runtime_enabled():
            self._roughcut_draft_pending = False
            self._set_roughcut_draft_status("disabled")
            if isinstance(settings_override, dict):
                self._roughcut_draft_settings_override = None
            self._roughcut_draft_manual_run_requested = False
            get_logger().log("⏭️ 러프컷 자동 실행 생략: 컷 경계/러프컷 런타임이 비활성화되어 있습니다.")
            return
        timer = getattr(self, "_roughcut_draft_timer", None)
        if timer is None:
            self._roughcut_draft_pending = False
            if isinstance(settings_override, dict):
                self._roughcut_draft_settings_override = None
            self._roughcut_draft_manual_run_requested = False
            return
        if force or not timer.isActive():
            self._roughcut_draft_pending = True
            self._set_roughcut_draft_status("queued")
            queue_text = "⏳ [러프컷 LLM] 수동 실행 대기" if manual_run else "⏳ [러프컷 LLM] 후처리 대기"
            self._mark_roughcut_queue_active(queue_text)
            if manual_run:
                get_logger().log("⏳ 러프컷 LLM 수동 실행 예약: 현재 저장된 자막 기준으로 중분류를 다시 만듭니다.")
            elif require_autorun:
                get_logger().log("⏳ 러프컷 LLM 후처리 예약: 자막 생성 완료 직후 중분류 초안을 이어서 만듭니다.")
            else:
                get_logger().log("⏳ 러프컷 LLM 후처리 예약: 부분 재인식 완료 후 중분류 초안을 갱신합니다.")
            timer.start(120 if force else 300)

    def _consume_cancelled_roughcut_timeout(self) -> bool:
        if not bool(getattr(self, "_roughcut_draft_cancelled", False)) or bool(
            getattr(self, "_roughcut_draft_manual_run_requested", False)
        ):
            return False
        self._roughcut_draft_pending = False
        self._set_roughcut_draft_status("idle")
        return True

    def _roughcut_draft_requeue(self, delay_ms: int) -> bool:
        timer = getattr(self, "_roughcut_draft_timer", None)
        if timer is None:
            return False
        self._roughcut_draft_pending = True
        self._set_roughcut_draft_status("queued")
        timer.start(int(delay_ms))
        return True

    def _roughcut_draft_segments_snapshot(self) -> list[dict]:
        return [
            dict(seg)
            for seg in self._get_current_segments()
            if not seg.get("is_gap") and str(seg.get("text", "") or "").strip()
        ]

    def _roughcut_draft_run_context(self, segments: list[dict], settings: dict) -> dict:
        main_w = self.window()
        media_path = str(getattr(self, "media_path", "") or "")
        media_files = list(getattr(main_w, "_multiclip_files", []) or [])
        if not media_files and media_path:
            media_files = [media_path]
        media_duration = max((float(seg.get("end", 0.0) or 0.0) for seg in segments), default=0.0)
        try:
            media_duration = max(media_duration, float(getattr(getattr(self, "video_player", None), "total_time", 0.0) or 0.0))
        except Exception:
            pass
        self._roughcut_draft_generation += 1
        confirmed = list(getattr(main_w, "_project_boundary_times", []) or [])
        provisional = list(getattr(self, "_auto_cut_boundary_scan_lines", []) or [])
        try:
            from core.roughcut.editor_draft import describe_editor_roughcut_llm_scope, estimate_editor_roughcut_llm_runtime_sec

            scope = describe_editor_roughcut_llm_scope(
                segments,
                settings,
                cut_boundaries=confirmed,
                provisional_cut_boundaries=provisional,
            )
            chunk_count = max(1, int(scope.get("chunk_count", 1) or 1))
            eta_sec = float(estimate_editor_roughcut_llm_runtime_sec(media_duration, settings) or 0.0)
        except Exception:
            chunk_count = 1
            eta_sec = 0.0
        eta_label = f" · 예상 {eta_sec:.0f}s" if eta_sec > 0.0 else ""
        manual_run = bool(getattr(self, "_roughcut_draft_manual_run_requested", False))
        return {
            "settings": settings,
            "main_w": main_w,
            "media_path": media_path,
            "media_files": media_files,
            "clip_boundaries": list(getattr(main_w, "_multiclip_boundaries", []) or []),
            "confirmed_cut_boundaries": confirmed,
            "provisional_cut_boundaries": provisional,
            "editor_mode": "multiclip" if len(media_files) > 1 else "single",
            "media_duration": media_duration,
            "source_media": f"멀티클립 {len(media_files)}개" if len(media_files) > 1 else os.path.basename(media_path or ""),
            "reference_major_segments": self._draft_reference_major_segments(),
            "reviewed_cut_boundaries": self._draft_reviewed_cut_boundaries(),
            "generation": int(self._roughcut_draft_generation),
            "manual_run": manual_run,
            "roughcut_chunk_count": chunk_count,
            "roughcut_eta_sec": eta_sec,
            "eta_label": eta_label,
            "log_label": "수동 실행" if manual_run else "후처리",
        }

    def _log_roughcut_draft_prepared(self, segments: list[dict], context: dict) -> None:
        queue_label = "수동 실행 중" if bool(context.get("manual_run")) else "후처리 중"
        eta_sec = float(context.get("roughcut_eta_sec", 0.0) or 0.0)
        eta_label = str(context.get("eta_label", "") or "")
        chunk_count = int(context.get("roughcut_chunk_count", 1) or 1)
        self._mark_roughcut_queue_active(
            f"🤖 [러프컷 LLM] {queue_label} · {chunk_count}chunk{eta_label}",
            expected_seconds=eta_sec if eta_sec > 0.0 else None,
        )
        get_logger().log(
            f"🤖 러프컷 {context.get('log_label', '후처리')} 준비: "
            f"자막 row {len(segments)}개 · chunk {chunk_count}개{eta_label}"
        )

    def _emit_roughcut_draft_candidate(self, llm_payload, refinement_source: str, *, segments: list[dict], context: dict) -> None:
        from core.roughcut import build_editor_roughcut_candidate_payload, build_editor_roughcut_draft_result

        settings = dict(context.get("settings") or {})
        result = build_editor_roughcut_draft_result(
            segments,
            media_duration=float(context.get("media_duration", 0.0) or 0.0),
            source_path=str(context.get("media_path", "") or ""),
            settings=settings,
            llm_payload=llm_payload,
            reference_major_segments=list(context.get("reference_major_segments") or []),
        )
        payload = build_editor_roughcut_candidate_payload(
            result,
            source_segments=segments,
            settings=settings,
            source_path=str(context.get("media_path", "") or ""),
            source_media=str(context.get("source_media", "") or ""),
            media_files=list(context.get("media_files") or []),
            clip_boundaries=list(context.get("clip_boundaries") or []),
            editor_mode=str(context.get("editor_mode", "single") or "single"),
        )
        payload["_generation"] = int(context.get("generation", 0) or 0)
        payload["refinement_source"] = refinement_source
        self.sig_roughcut_draft_ready.emit(result, segments, payload)

    def _emit_local_roughcut_draft(self, segments: list[dict], context: dict, source: str, message: str) -> None:
        try:
            get_logger().log(message)
            self._emit_roughcut_draft_candidate(None, source, segments=segments, context=context)
        except Exception as exc:
            self._set_roughcut_draft_status("failed")
            get_logger().log(f"⚠️ 에디터 러프컷 로컬 초안 생성 실패: {exc}")

    def _roughcut_draft_llm_ready(self, settings: dict, segments: list[dict]) -> bool:
        try:
            from core.roughcut import resolve_roughcut_llm_config

            llm_config = resolve_roughcut_llm_config(settings, subtitle_rows=list(segments or []))
            provider = str(getattr(llm_config, "provider", "") or "").strip().lower()
            model = str(getattr(llm_config, "model", "") or "").strip()
            return bool(getattr(llm_config, "enabled", False)) and provider != "none" and model and "사용 안함" not in model
        except Exception:
            model = str(settings.get("selected_model", "") or "").strip()
            return bool(model and "사용 안함" not in model)

    def _roughcut_draft_can_run_llm(self, segments: list[dict], context: dict) -> bool:
        settings = dict(context.get("settings") or {})
        manual_run = bool(context.get("manual_run", False))
        generation = int(context.get("generation", 0) or 0)
        try:
            min_count = max(1, int(settings.get("roughcut_major_min_subtitle_count", 5) or 5))
        except Exception:
            min_count = 5
        if not self._roughcut_draft_llm_ready(settings, segments):
            if manual_run:
                self.sig_roughcut_draft_ready.emit(None, [], {"_generation": generation, "refinement_source": "failed"})
                get_logger().log("⚠️ 러프컷 LLM 수동 실행 실패: 사용할 LLM 모델 설정이 없습니다.")
            else:
                self._emit_local_roughcut_draft(
                    segments,
                    context,
                    "local_after_generation",
                    "⏩ 러프컷 후처리: 사용할 LLM 모델 설정이 없어 로컬 규칙 초안으로 마무리합니다.",
                )
            return False
        if len(segments) < min_count and not manual_run:
            self._emit_local_roughcut_draft(
                segments,
                context,
                "local_after_generation",
                f"⏩ 러프컷 후처리: 자막 row {len(segments)}개가 LLM 최소 기준 {min_count}개 미만이라 로컬 규칙 초안으로 마무리합니다.",
            )
            return False
        if self._post_generation_local_llm_release_requested(settings, segments):
            self._roughcut_llm_cooldown_until = time.time() + 10.0
            self._emit_local_roughcut_draft(
                segments,
                context,
                "local_after_generation_runtime_released",
                "⏩ 러프컷 LLM: 에디터 모드 모델 정리 요청 상태라 로컬 규칙 초안으로 즉시 대체합니다.",
            )
            return False
        return self._roughcut_draft_context_allows_llm(segments, context)

    def _roughcut_draft_context_allows_llm(self, segments: list[dict], context: dict) -> bool:
        settings = dict(context.get("settings") or {})
        manual_run = bool(context.get("manual_run", False))
        generation = int(context.get("generation", 0) or 0)
        try:
            from core.roughcut import describe_editor_roughcut_llm_scope, editor_roughcut_draft_llm_allowed, resolve_roughcut_context_policy

            scope = describe_editor_roughcut_llm_scope(
                segments,
                settings,
                cut_boundaries=list(context.get("confirmed_cut_boundaries") or []),
                provisional_cut_boundaries=list(context.get("provisional_cut_boundaries") or []),
            )
            if str(scope.get("mode") or "") == "chunked":
                get_logger().log(
                    "✂️ 긴 영상 러프컷: 자막 row "
                    f"{len(segments)}개를 컷 경계 기반 {int(scope.get('chunk_count', 0) or 0)}개 chunk로 나눠 LLM 초안을 순차 생성합니다."
                )
            if editor_roughcut_draft_llm_allowed(
                segments,
                settings,
                cut_boundaries=list(context.get("confirmed_cut_boundaries") or []),
                provisional_cut_boundaries=list(context.get("provisional_cut_boundaries") or []),
            ):
                return self._roughcut_draft_cooldown_allows_llm(segments, context)
            policy = resolve_roughcut_context_policy(settings, subtitle_rows=list(segments or []))
            max_rows = int(policy.get("max_context_rows", settings.get("roughcut_llm_max_context_rows", 80)) or 80)
            get_logger().log(
                f"⏩ 긴 영상 러프컷: 자막 row가 {len(segments)}개라 자동 문맥 정책({max_rows}개 제한)으로 "
                "LLM 초안을 건너뛰고 로컬 세그먼트를 즉시 생성합니다."
            )
            if manual_run:
                self.sig_roughcut_draft_ready.emit(None, [], {"_generation": generation, "refinement_source": "failed"})
            else:
                self._emit_roughcut_draft_candidate(None, "local_after_generation_long_video", segments=segments, context=context)
            return False
        except Exception as exc:
            if manual_run:
                self.sig_roughcut_draft_ready.emit(None, [], {"_generation": generation, "refinement_source": "failed"})
                get_logger().log(f"⚠️ 러프컷 LLM 수동 실행 길이 판단 실패: {exc}")
            else:
                get_logger().log(f"⚠️ 러프컷 LLM 길이 판단 실패, 로컬 초안으로 진행: {exc}")
                self._emit_roughcut_draft_candidate(None, "local_after_generation_length_guard", segments=segments, context=context)
            return False

    def _roughcut_draft_cooldown_allows_llm(self, segments: list[dict], context: dict) -> bool:
        if time.time() >= float(getattr(self, "_roughcut_llm_cooldown_until", 0.0) or 0.0):
            return True
        if bool(context.get("manual_run", False)):
            self._roughcut_llm_cooldown_until = 0.0
            return True
        self._emit_local_roughcut_draft(
            segments,
            context,
            "local_after_generation",
            "⏩ 러프컷 후처리: LLM cooldown 중이라 로컬 규칙 초안으로 마무리합니다.",
        )
        return False

    def _start_roughcut_draft_llm_worker(self, segments: list[dict], context: dict) -> None:
        def worker():
            try:
                from core.roughcut import run_editor_roughcut_llm_draft

                get_logger().log(
                    f"🤖 러프컷 LLM {context.get('log_label', '후처리')} 실행: "
                    f"자막 row {len(segments)}개 · chunk {int(context.get('roughcut_chunk_count', 1) or 1)}개"
                    f"{context.get('eta_label', '') or ''}"
                )
                payload = run_editor_roughcut_llm_draft(
                    segments,
                    settings=dict(context.get("settings") or {}),
                    cut_boundaries=list(context.get("confirmed_cut_boundaries") or []),
                    provisional_cut_boundaries=list(context.get("provisional_cut_boundaries") or []),
                    reference_major_segments=list(context.get("reference_major_segments") or []),
                    reviewed_cut_boundaries=list(context.get("reviewed_cut_boundaries") or []),
                )
                if payload is None:
                    self._roughcut_llm_cooldown_until = time.time() + 10.0
                    if bool(context.get("manual_run", False)):
                        get_logger().log("⚠️ 러프컷 LLM 수동 실행 결과 없음: 기존 중분류를 유지합니다.")
                        self.sig_roughcut_draft_ready.emit(None, [], {"_generation": int(context.get("generation", 0) or 0), "refinement_source": "failed"})
                        return
                    get_logger().log("↩️ 러프컷 LLM 후처리 결과 없음: 로컬 규칙 초안으로 마무리합니다.")
                    self._emit_roughcut_draft_candidate(None, "local_after_generation_fallback", segments=segments, context=context)
                else:
                    self._roughcut_llm_cooldown_until = 0.0
                    get_logger().log("✅ 러프컷 LLM 응답 수신: 초안 저장 단계로 넘깁니다.")
                    self._emit_roughcut_draft_candidate(payload, "llm_refined", segments=segments, context=context)
            except Exception as exc:
                self.sig_roughcut_draft_ready.emit(None, [], {"_generation": int(context.get("generation", 0) or 0), "refinement_source": "failed"})
                try:
                    get_logger().log(f"⚠️ 에디터 러프컷 초안 생성 실패: {exc}")
                except Exception:
                    pass

        self._roughcut_draft_pending = False
        self._roughcut_draft_thread = threading.Thread(target=worker, daemon=True, name="editor-post-generation-roughcut-draft")
        self._roughcut_draft_thread.start()

    def _run_post_generation_roughcut_draft(self):
        if self._consume_cancelled_roughcut_timeout():
            return
        if not self._roughcut_draft_runtime_enabled():
            self._roughcut_draft_pending = False
            self._set_roughcut_draft_status("disabled")
            self._roughcut_draft_settings_override = None
            self._roughcut_draft_manual_run_requested = False
            return
        if not self._cut_boundary_runtime_settled_for_roughcut():
            self._roughcut_draft_requeue(900)
            return
        if self._roughcut_playback_active():
            self._roughcut_draft_requeue(2200)
            return
        thread = getattr(self, "_roughcut_draft_thread", None)
        if thread is not None and thread.is_alive():
            return
        segments = self._roughcut_draft_segments_snapshot()
        if not segments:
            self._roughcut_draft_pending = False
            self._set_roughcut_draft_status("idle")
            self._mark_roughcut_queue_done()
            self._roughcut_draft_settings_override = None
            self._roughcut_draft_manual_run_requested = False
            return
        self._roughcut_draft_pending = True
        self._set_roughcut_draft_status("running")

        settings = self._draft_settings_snapshot()
        context = self._roughcut_draft_run_context(segments, settings)
        self._log_roughcut_draft_prepared(segments, context)
        if self._roughcut_draft_can_run_llm(segments, context):
            # LLM 실행은 thread로 넘기고, 준비/로컬 fallback 판정은 UI thread에서 끝낸다.
            self._start_roughcut_draft_llm_worker(segments, context)

    def _apply_post_generation_roughcut_draft(self, result, segments: list, candidate: dict):
        candidate = dict(candidate or {})
        refinement_source = str(candidate.get("refinement_source") or "")
        try:
            if int(candidate.get("_generation", -1)) != int(getattr(self, "_roughcut_draft_generation", 0)):
                return
        except Exception:
            pass
        if refinement_source == "failed":
            self._set_roughcut_draft_status("failed")
            self._roughcut_draft_pending = False
            self._roughcut_draft_thread = None
            self._roughcut_draft_settings_override = None
            self._roughcut_draft_manual_run_requested = False
            self._mark_roughcut_queue_done(note="러프컷 미적용")
            self._schedule_post_roughcut_model_release()
            return
        self._set_roughcut_draft_status("saving")
        self._mark_roughcut_queue_active("💾 [러프컷 LLM] 저장 중")
        result = self._sorted_roughcut_result(result)
        try:
            major_count = len(getattr(result, "segments", ()) or ())
            max_major = int(self._draft_settings_snapshot().get("editor_roughcut_draft_max_major_segments", 10) or 10)
            if major_count > max(1, min(26, max_major)):
                from core.roughcut import build_editor_roughcut_candidate_payload, build_editor_roughcut_draft_result

                settings = self._draft_settings_snapshot()
                media_path = str(getattr(self, "media_path", "") or "")
                main_w = self.window()
                media_files = list(getattr(main_w, "_multiclip_files", []) or [])
                if not media_files and media_path:
                    media_files = [media_path]
                result = build_editor_roughcut_draft_result(
                    segments,
                    media_duration=max((float(seg.get("end", 0.0) or 0.0) for seg in segments), default=0.0),
                    source_path=media_path,
                    settings=settings,
                    llm_payload=None,
                    reference_major_segments=self._draft_reference_major_segments(),
                )
                candidate = build_editor_roughcut_candidate_payload(
                    result,
                    source_segments=segments,
                    settings=settings,
                    source_path=media_path,
                    source_media=os.path.basename(media_path or "") or "현재 에디터",
                    media_files=media_files,
                    clip_boundaries=list(getattr(main_w, "_multiclip_boundaries", []) or []),
                    editor_mode="multiclip" if len(media_files) > 1 else "single",
                )
                candidate["refinement_source"] = refinement_source or "local_capped"
        except Exception:
            pass
        result = self._sorted_roughcut_result(result)
        candidate["segments"] = self._sorted_roughcut_middle_rows(candidate.get("segments", []))
        main_w = self.window()
        project_path = str(getattr(main_w, "_current_project_path", "") or "")
        if not project_path:
            try:
                from core.path_manager import get_srt_path
                from core.project.project_manager import create_project

                media_path = str(getattr(self, "media_path", "") or "")
                if media_path:
                    project_path = create_project(
                        name=os.path.splitext(os.path.basename(media_path))[0],
                        media_paths=[media_path],
                        srt_path=get_srt_path(media_path),
                        user_settings=dict(getattr(self, "settings", {}) or {}),
                        prefill_analysis_artifacts=False,  # 프로젝트 생성만 하고 생성 prefill LLM 재진입은 막는다.
                    )
                    attach_project_session(
                        main_w,
                        project_path,
                        None,
                        auto_pipeline=False,
                        clear_multiclip=False,
                        emit_boundary_signal=False,
                    )
            except Exception as exc:
                get_logger().log(f"⚠️ 러프컷 초안 프로젝트 생성 실패: {exc}")
        if not project_path:
            self._set_roughcut_draft_status("failed")
            self._mark_roughcut_queue_done(note="러프컷 미적용")
            self._roughcut_draft_settings_override = None
            self._roughcut_draft_manual_run_requested = False
            self._schedule_post_roughcut_model_release()
            return
        try:
            from core.project.project_manager import save_project_roughcut_state
            from core.project.project_io import read_project_file
            from core.roughcut import EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID, merge_editor_roughcut_draft_state
            from core.work_mode import EDITOR_MODE

            existing_state = {}
            if os.path.exists(project_path):
                try:
                    existing_state = read_project_file(project_path).get("roughcut_state", {}) or {}
                except Exception:
                    existing_state = {}
            candidate.pop("_generation", None)
            roughcut_state = merge_editor_roughcut_draft_state(existing_state, candidate)
            save_project_roughcut_state(
                project_path,
                middle_segments=list(candidate.get("segments", []) or []),
                roughcut_result=candidate,
                preliminary_middle_segments=(
                    list(candidate.get("segments", []) or [])
                    if refinement_source == "llm_refined"
                    else []
                ),
                roughcut_state=roughcut_state,
                active_work_mode=EDITOR_MODE,
            )
            self._pending_preliminary_middle_segments = (
                list(candidate.get("segments", []) or [])
                if refinement_source == "llm_refined"
                else []
            )
            self._apply_roughcut_middle_segments_to_ui(list(candidate.get("segments", []) or []), result)
            setattr(main_w, "_editor_roughcut_result", result)
            roughcut = getattr(main_w, "_roughcut_widget", None)
            if roughcut is not None:
                try:
                    roughcut._result = result
                    roughcut._source_signature = str(candidate.get("source_signature") or "")
                    roughcut._selected_candidate_id = EDITOR_ROUGHCUT_DRAFT_CANDIDATE_ID
                    roughcut._roughcut_candidates = list(roughcut_state.get("candidates", []) or [])
                    if hasattr(roughcut, "_refresh_candidate_combo"):
                        roughcut._refresh_candidate_combo()
                    if hasattr(roughcut, "_populate_result"):
                        roughcut._populate_result()
                except RuntimeError:
                    pass
                except Exception:
                    pass
            self._redraw_timeline()
            count = len(getattr(result, "segments", ()) or ())
            last_count = getattr(self, "_last_roughcut_draft_major_count", None)
            if last_count != count:
                self._last_roughcut_draft_major_count = count
                source_label = "LLM" if refinement_source == "llm_refined" else "로컬"
                get_logger().log(f"✅ 러프컷 후처리 완료: {source_label} 초안 · 중분류 {count}개")
            self._set_roughcut_draft_status("done", count)
            self._mark_roughcut_queue_done()
        except Exception as exc:
            self._set_roughcut_draft_status("failed")
            self._mark_roughcut_queue_done(note="러프컷 미적용")
            get_logger().log(f"⚠️ 러프컷 초안 저장 실패: {exc}")
        finally:
            self._roughcut_draft_pending = False
            self._ensure_post_generation_editor_interactive()
            try:
                self._pending_preliminary_middle_segments = []
            except Exception:
                pass
            self._schedule_post_roughcut_model_release()
            self._roughcut_draft_settings_override = None
            self._roughcut_draft_manual_run_requested = False
            self._roughcut_draft_thread = None
