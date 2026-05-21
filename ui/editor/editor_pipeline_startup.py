# Version: 01.00.00
# Phase: PHASE2
from __future__ import annotations

import os
import time

from PyQt6.QtCore import QTimer

from core.path_manager import get_srt_path
from core.project.project_manager import create_project
from ui.editor.editor_pipeline_safety import EditorPipelineSafetyMixin
from ui.project.project_session_runtime import attach_project_session


class EditorPipelineStartupMixin(EditorPipelineSafetyMixin):
    def _trigger_auto_start(self):
        if not hasattr(self, "btn_start"):
            return
        from core.state_manager import SubtitleStateManager

        if self.sm.state == SubtitleStateManager.ST_IDLE:
            self._on_start_clicked()

    def _tick_spinner(self):
        try:
            self._spinner_idx = (self._spinner_idx + 1) % len(self._spinner_frames)
        except RuntimeError:
            pass

    def _start_pipeline(self, is_restart=False):
        main_w = self._pipeline_window()
        layout_snapshot = self._snapshot_start_layout()
        self._show_pipeline_start_feedback(is_restart=is_restart)
        self._pipeline_call_if_callable(
            main_w,
            "_lock_workspace_sidebar_width",
            label="사이드바 폭 잠금",
            log=False,
        )
        self._pipeline_call_if_callable(
            main_w,
            "_set_runtime_audio_tune_display",
            "",
            {"tune": {}},
            label="런타임 오디오 표시 초기화",
            log=False,
        )
        self._pipeline_call_if_callable(
            main_w,
            "_stop_post_completion_idle_timer",
            label="생성 완료 idle timer 중지",
            log=False,
        )
        self._pipeline_call_if_callable(
            self,
            "_load_deferred_open_waveform",
            label="시작 후 지연 waveform 로드",
            log=False,
        )
        try:
            from core.settings import load_settings

            latest_settings = load_settings()
            if latest_settings:
                self.settings.update(latest_settings)
                self._pipeline_call_if_callable(
                    self,
                    "_refresh_speaker_strip",
                    label="화자 스트립 새로고침",
                    log=False,
                )
        except Exception as exc:
            self._pipeline_log_nonfatal("최신 설정 로드", exc)
        self._completion_handled = False
        self._process_completed_finalized = False
        self._generation_completion_autosave_done = False
        self._generation_completion_autosave_pending = False

        if not is_restart:
            try:
                if main_w is not None:
                    self._pipeline_call_if_callable(
                        main_w,
                        "_clear_editor_for_full_restart",
                        self,
                        label="시작 전 에디터 상태 초기화",
                    )
                    self._pipeline_call_if_callable(
                        main_w,
                        "_clear_cut_boundary_state_for_full_restart",
                        self,
                        label="시작 전 컷 경계 상태 초기화",
                    )
                if main_w is not None and hasattr(main_w, "_clear_roughcut_for_full_restart"):
                    media_files = list(getattr(main_w, "_multiclip_files", []) or [])
                    if not media_files:
                        media_path = getattr(self, "media_path", "") or ""
                        media_files = [media_path] if media_path else []
                    self._pipeline_call_if_callable(
                        main_w,
                        "_clear_roughcut_for_full_restart",
                        media_files,
                        label="시작 전 러프컷 상태 초기화",
                    )
            except Exception as exc:
                self._pipeline_log_nonfatal("시작 전 이전 캔버스 상태 초기화", exc)

        try:
            self._prepare_cut_boundaries_before_start()
        except Exception as e:
            self._pipeline_log_nonfatal("컷 경계 사전 스캔", e)

        self._process_start_time = time.time()
        self._backend_finished = False
        self._execute_pipeline_logic(is_restart)
        self._restore_start_layout(layout_snapshot)

    def _show_pipeline_start_feedback(self, *, is_restart: bool = False) -> None:
        """Make the Start click visibly acknowledge before setup work runs."""
        try:
            if getattr(self, "is_auto_start", False):
                self.sm.start_auto_mode()
            elif is_restart:
                self.sm.start_processing()
            else:
                self.sm.start_ai_all()
            self.sm.set_custom_status("⏳ 재시작 준비 중..." if is_restart else "⏳ 시작 준비 중...")
        except Exception as exc:
            self._pipeline_log_nonfatal("시작 상태 표시", exc)
            return
        main_w = self._pipeline_window()
        self._pipeline_call_if_callable(
            main_w,
            "sync_menu_from_editor",
            self,
            label="시작 상태 메뉴 동기화",
            log=False,
        )
        try:
            from PyQt6.QtCore import QEventLoop
            from PyQt6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                app.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        except Exception as exc:
            self._pipeline_log_nonfatal("시작 직전 UI flush", exc)

    def _snapshot_start_layout(self) -> dict:
        """Capture layout sizes that should not shift just because processing starts."""
        snap = {}
        try:
            main_w = self.window()
        except RuntimeError:
            main_w = None
        for key, owner, attr in (
            ("workspace_splitter", main_w, "workspace_splitter"),
            ("editor_splitter", self, "splitter"),
        ):
            splitter = getattr(owner, attr, None) if owner is not None else None
            if splitter is None:
                continue
            result = self._pipeline_best_effort(
                lambda splitter=splitter: list(splitter.sizes()),
                label=f"{key} splitter snapshot",
                default=None,
                log=False,
            )
            if result is not None:
                snap[key] = result
        panel = getattr(main_w, "bottom_work_panel", None) if main_w is not None else None
        if panel is not None:
            panel_state = self._pipeline_best_effort(
                lambda: {
                    "visible": bool(panel.isVisible()),
                    "maximum_height": int(panel.maximumHeight()),
                    "minimum_height": int(panel.minimumHeight()),
                },
                label="bottom panel snapshot",
                default=None,
                log=False,
            )
            if panel_state is not None:
                snap["bottom_work_panel"] = panel_state
        stable_frames = {}
        for attr in ("editor_frame", "video_frame", "timeline_frame"):
            frame = getattr(self, attr, None)
            if frame is None:
                continue
            frame_state = self._pipeline_best_effort(
                lambda frame=frame: {
                    "minimum_width": int(frame.minimumWidth()),
                    "minimum_height": int(frame.minimumHeight()),
                    "maximum_height": int(frame.maximumHeight()),
                    "height": max(int(frame.height()), int(frame.minimumHeight()), int(frame.minimumSizeHint().height())),
                },
                label=f"{attr} frame snapshot",
                default=None,
                log=False,
            )
            if frame_state is not None:
                stable_frames[attr] = frame_state
        if stable_frames:
            snap["stable_frames"] = stable_frames
        return snap

    def _restore_start_layout(self, snap: dict | None) -> None:
        if not snap:
            return

        def _restore_once():
            try:
                main_w = self.window()
            except RuntimeError:
                return
            for key, owner, attr in (
                ("workspace_splitter", main_w, "workspace_splitter"),
                ("editor_splitter", self, "splitter"),
            ):
                sizes = list((snap or {}).get(key) or [])
                splitter = getattr(owner, attr, None) if owner is not None else None
                if splitter is None or not sizes:
                    continue
                self._pipeline_best_effort(
                    lambda splitter=splitter, sizes=sizes: splitter.setSizes(sizes) if len(splitter.sizes()) == len(sizes) else None,
                    label=f"{key} splitter restore",
                    log=False,
                )
            panel_state = (snap or {}).get("bottom_work_panel")
            panel = getattr(main_w, "bottom_work_panel", None)
            if panel is not None and isinstance(panel_state, dict):
                self._pipeline_best_effort(
                    lambda: (
                        panel.setMinimumHeight(int(panel_state.get("minimum_height", panel.minimumHeight()))),
                        panel.setMaximumHeight(int(panel_state.get("maximum_height", panel.maximumHeight()))),
                        panel.setVisible(bool(panel_state.get("visible", panel.isVisible()))),
                    ),
                    label="bottom panel restore",
                    log=False,
                )
            for attr, frame_state in dict((snap or {}).get("stable_frames") or {}).items():
                frame = getattr(self, attr, None)
                if frame is None or not isinstance(frame_state, dict):
                    continue
                self._pipeline_best_effort(
                    lambda frame=frame, attr=attr, frame_state=frame_state: (
                        frame.refresh_render_policy() if hasattr(frame, "refresh_render_policy") else None,
                        frame.setMinimumWidth(int(frame_state.get("minimum_width", frame.minimumWidth()))),
                        frame.setMinimumHeight(int(frame_state.get("minimum_height", frame.minimumHeight()))),
                        frame.setFixedHeight(int(frame_state.get("height", frame.height()))) if attr == "timeline_frame" else None,
                        frame.updateGeometry(),
                    ),
                    label=f"{attr} frame restore",
                    log=False,
                )

        for delay in (0, 60, 180, 360, 720, 1200):
            QTimer.singleShot(delay, _restore_once)

    def _prepare_cut_boundaries_before_start(self):
        main_w = self._pipeline_window()
        backend = getattr(main_w, "backend", None)
        media_files = list(getattr(main_w, "_multiclip_files", []) or [])
        if not media_files:
            media_path = getattr(self, "media_path", "") or ""
            if media_path:
                media_files = [media_path]
        if not media_files:
            return

        project_path = str(getattr(main_w, "_current_project_path", "") or "")
        if not project_path:
            base_name = os.path.splitext(os.path.basename(media_files[0]))[0]
            project_path = create_project(
                name=base_name,
                media_paths=media_files,
                srt_path=get_srt_path(media_files[0]),
                user_settings=dict(getattr(self, "settings", {}) or {}),
                prefill_analysis_artifacts=False,
            )
            attach_project_session(
                main_w,
                project_path,
                None,
                auto_pipeline=False,
                clear_multiclip=False,
                emit_boundary_signal=False,
            )

        if backend is not None and hasattr(backend, "_auto_scan_cut_boundaries_for_start"):
            self._pipeline_best_effort(
                lambda: (
                    setattr(backend, "_force_cut_boundary_rescan_once", True),
                    setattr(backend, "_cut_boundary_prescan_completed", False),
                ),
                label="컷 경계 prescan 재강제",
                log=False,
            )
            backend._auto_scan_cut_boundaries_for_start(project_path, media_files)

    def _execute_pipeline_logic(self, is_restart):
        main_w = self.window()
        if not self.text_edit.toPlainText().strip():
            self.text_edit.clear()
        self._segment_queue.clear()

        if is_restart:
            if hasattr(main_w, "backend") and main_w.backend:
                main_w.backend.restart_current_file()
            self._spinner_timer.start()
        else:
            self.sig_start.emit()
            self._spinner_timer.start()

        QTimer.singleShot(50, self._safe_enable_start_btn)

    def _on_start_clicked(self):
        from core.state_manager import SubtitleStateManager

        if getattr(self, "_stt_mode_enabled", False):
            if hasattr(self, "_start_stt_vad_detection") and self._start_stt_vad_detection():
                return
        if self.sm.state == SubtitleStateManager.ST_PROC:
            self._stop_pipeline()
        elif self.sm.state in [SubtitleStateManager.ST_COMP, SubtitleStateManager.ST_SAVED]:
            main_w = self.window()
            restarted = False
            if hasattr(main_w, "_restart_current_pipeline_from_beginning"):
                restarted = main_w._restart_current_pipeline_from_beginning(self)
            if restarted:
                self.sm.start_processing()
                if hasattr(self, "_spinner_timer"):
                    self._spinner_timer.start()
                return
            self._start_pipeline(is_restart=True)
        else:
            self._start_pipeline(is_restart=False)
