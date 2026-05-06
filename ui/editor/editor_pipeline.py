# Version: 03.14.03
# Phase: PHASE2
"""
ui/editor_pipeline.py
[v01.00.16] 모드/상태 정의 문서 반영
- _on_save: is_locked 체크 제거 (상태 무관 저장)
- _on_prev: 생성 중 중단 + 단일 다이얼로그 (main_window 중복 제거)
- update_progress: 완료 조건 단일화 (EditorPipeline만 완료 판단)
- 기존 기능 100% 유지
"""
import os, time, threading, queue
from PyQt6.QtWidgets import QMenu
from PyQt6.QtCore import QTimer, QObject, pyqtSignal

from core.runtime import config
from core.runtime.logger import get_logger
from core.project.project_manager import create_project
from core.path_manager import get_srt_path


class PartialSignals(QObject):
    status = pyqtSignal(str, str)
    progress = pyqtSignal(int, int)
    chunk_time = pyqtSignal(float)
    done = pyqtSignal(list)
    finished = pyqtSignal()


class EditorPipelineMixin:
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

    # ---------------------------------------------------------
    # Backend Signal Hook
    # ---------------------------------------------------------
    def _hook_backend_signals(self):
        main_w = self.window()
        try:
            if hasattr(self, "_connect_cut_boundary_placeholder_signal"):
                self._connect_cut_boundary_placeholder_signal()
        except Exception:
            pass
        if hasattr(main_w, "backend") and main_w.backend:
            try: main_w.backend.sig_chunk_done.disconnect(self.append_segments)
            except Exception: pass
            try: main_w.backend.sig_progress.disconnect(self.update_progress)
            except Exception: pass
            try: main_w.backend.sig_chunk_done.connect(self.append_segments)
            except Exception: pass
            try: main_w.backend.sig_progress.connect(self.update_progress)
            except Exception: pass
            if getattr(self, 'is_batch_mode', False) and hasattr(main_w.backend, 'sig_batch_finished'):
                try: main_w.backend.sig_batch_finished.disconnect()
                except Exception: pass
                main_w.backend.sig_batch_finished.connect(self._on_batch_finished)

    def _on_batch_finished(self):
        self.sm.set_custom_status("✅ 배치 작업이 모두 완료되었습니다.")
        self._send_ntfy_batch_complete()

    def _send_ntfy_batch_complete(self):
        try:
            main_w = self.window()
            if not getattr(main_w, '_is_auto_pipeline', False):
                return
            from core.notifier import send_ntfy
            send_ntfy(
                title=f"🎉 {config.APP_NAME} 알림",
                message="🎬 모든 파일의 자막 생성이 완료되었습니다!",
                tags="tada,sparkles,clapper"
            )
        except Exception:
            pass

    # ---------------------------------------------------------
    # Pipeline & State Machine Logic
    # ---------------------------------------------------------
    def _trigger_auto_start(self):
        if not hasattr(self, 'btn_start'): return
        from core.state_manager import SubtitleStateManager
        if self.sm.state == SubtitleStateManager.ST_IDLE:
            self._on_start_clicked()

    def _tick_spinner(self):
        try:
            self._spinner_idx = (self._spinner_idx + 1) % len(self._spinner_frames)
        except RuntimeError: pass

    def _safe_enable_start_btn(self):
        try:
            if hasattr(self, 'btn_start') and self.btn_start:
                self.btn_start.setEnabled(True)
        except RuntimeError: pass

    def _stop_pipeline(self):
        main_w = self.window()
        if hasattr(main_w, "_stop_post_completion_idle_timer"):
            main_w._stop_post_completion_idle_timer()
        self.sm.stop_processing("작업이 중지되었습니다.")
        if hasattr(self, '_spinner_timer'): self._spinner_timer.stop()
        active_backend = None
        if hasattr(main_w, "backend_fast") and getattr(main_w.backend_fast, "_active", False):
            active_backend = main_w.backend_fast
        elif hasattr(main_w, "backend") and main_w.backend:
            active_backend = main_w.backend
        if active_backend is not None:
            active_backend.stop(log_context="작업 중지")
        QTimer.singleShot(1000, self._safe_enable_start_btn)

    def _start_pipeline(self, is_restart=False):
        main_w = self.window()
        layout_snapshot = self._snapshot_start_layout()
        if hasattr(main_w, "_stop_post_completion_idle_timer"):
            main_w._stop_post_completion_idle_timer()
        try:
            from core.settings import load_settings
            latest_settings = load_settings()
            if latest_settings:
                self.settings.update(latest_settings)
                if hasattr(self, "_refresh_speaker_strip"):
                    self._refresh_speaker_strip()
        except Exception:
            pass
        self._completion_handled = False

        if not is_restart:
            try:
                main_w = self.window()
                if hasattr(main_w, "_clear_editor_for_full_restart"):
                    main_w._clear_editor_for_full_restart(self)
                if hasattr(main_w, "_clear_cut_boundary_state_for_full_restart"):
                    main_w._clear_cut_boundary_state_for_full_restart(self)
                if hasattr(main_w, "_clear_roughcut_for_full_restart"):
                    media_files = list(getattr(main_w, "_multiclip_files", []) or [])
                    if not media_files:
                        media_path = getattr(self, "media_path", "") or ""
                        media_files = [media_path] if media_path else []
                    main_w._clear_roughcut_for_full_restart(media_files)
            except Exception as exc:
                try:
                    get_logger().log(f"⚠️ 시작 전 이전 캔버스 상태 초기화 실패: {exc}")
                except Exception:
                    pass

        # ✅ 컷 경계 기반 러프컷 선구성: STT 시작 전에 컷 경계 먼저 스캔
        try:
            self._prepare_cut_boundaries_before_start()
        except Exception as e:
            try:
                get_logger().log(f"⚠️ 컷 경계 사전 스캔 실패: {e}")
            except Exception:
                pass

        if getattr(self, 'is_auto_start', False):
            self.sm.start_auto_mode()
        else:
            self.sm.start_ai_all()
        self._process_start_time = time.time()
        self._backend_finished = False
        self._execute_pipeline_logic(is_restart)
        self._restore_start_layout(layout_snapshot)

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
            try:
                snap[key] = list(splitter.sizes())
            except Exception:
                pass
        panel = getattr(main_w, "bottom_work_panel", None) if main_w is not None else None
        if panel is not None:
            try:
                snap["bottom_work_panel"] = {
                    "visible": bool(panel.isVisible()),
                    "maximum_height": int(panel.maximumHeight()),
                    "minimum_height": int(panel.minimumHeight()),
                }
            except Exception:
                pass
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
                try:
                    if len(splitter.sizes()) == len(sizes):
                        splitter.setSizes(sizes)
                except Exception:
                    pass
            panel_state = (snap or {}).get("bottom_work_panel")
            panel = getattr(main_w, "bottom_work_panel", None)
            if panel is not None and isinstance(panel_state, dict):
                try:
                    panel.setMinimumHeight(int(panel_state.get("minimum_height", panel.minimumHeight())))
                    panel.setMaximumHeight(int(panel_state.get("maximum_height", panel.maximumHeight())))
                    panel.setVisible(bool(panel_state.get("visible", panel.isVisible())))
                except Exception:
                    pass

        for delay in (0, 60, 180, 360):
            QTimer.singleShot(delay, _restore_once)

    def _prepare_cut_boundaries_before_start(self):
        main_w = self.window()
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
            )
            main_w._current_project_path = project_path

        if backend is not None and hasattr(backend, "_auto_scan_cut_boundaries_for_start"):
            backend._auto_scan_cut_boundaries_for_start(project_path, media_files)

    def _set_process_completed(self):
        if hasattr(self, "_flush_pending_segment_queue_now"):
            self._flush_pending_segment_queue_now()
        if getattr(self, 'is_auto_start', False):
            self.sm.complete_auto_mode()
        else:
            self.sm.complete_ai()
        if hasattr(self, '_spinner_timer'): self._spinner_timer.stop()
        get_logger().log("✅ 자막 생성 완료 (EditorPipeline 확정)")
        main_w = self.window()
        if hasattr(main_w, "sync_menu_from_editor"):
            main_w.sync_menu_from_editor(self)
        if hasattr(main_w, "_refresh_saved_status_label"):
            main_w._refresh_saved_status_label(is_dirty=True)
        if hasattr(main_w, "_start_post_completion_idle_timer"):
            main_w._start_post_completion_idle_timer()
        try:
            from core.personalization.text_lora_dataset import accumulate_personalization_dataset

            accumulate_personalization_dataset(
                current_segments=[dict(seg) for seg in list(self._get_current_segments() or []) if not seg.get("is_gap")],
                current_project_path=str(getattr(main_w, "_current_project_path", "") or ""),
                trigger="generation_complete",
            )
        except Exception as exc:
            get_logger().log(f"⚠️ 개인화 데이터 누적 실패(생성완료): {exc}")
        if hasattr(self, "_schedule_post_generation_roughcut_draft"):
            QTimer.singleShot(350, lambda: self._schedule_post_generation_roughcut_draft(force=True))
        if hasattr(main_w, "_release_ai_models_for_editor_mode"):
            QTimer.singleShot(450, self._schedule_post_generation_model_release)
        # E fix: 자막 생성 완료 후 타임라인/캔버스 재동기화
        QTimer.singleShot(200, self._post_completion_sync)

    def _schedule_post_generation_model_release(self):
        """자막 생성 완료 후 남아 있는 AI/STT/LLM 모델 언로드를 예약한다."""
        try:
            if hasattr(self, "_schedule_post_generation_roughcut_draft"):
                self._release_ai_models_after_roughcut_draft()
                return
            main_w = self.window()
        except RuntimeError:
            return
        except Exception:
            return
        release = getattr(main_w, "_release_ai_models_for_editor_mode", None)
        if callable(release):
            release(force=True)

    def _roughcut_draft_cleanup_pending(self) -> bool:
        status = str(getattr(self, "_roughcut_draft_status", "") or "")
        if status in {"queued", "running", "saving"}:
            return True
        try:
            timer = getattr(self, "_roughcut_draft_timer", None)
            if timer is not None and timer.isActive():
                return True
        except RuntimeError:
            return False
        except Exception:
            pass
        try:
            thread = getattr(self, "_roughcut_draft_thread", None)
            if thread is not None and thread.is_alive():
                return True
        except Exception:
            pass
        return bool(getattr(self, "_roughcut_draft_pending", False))

    def _release_ai_models_after_roughcut_draft(self):
        import threading
        is_busy = self._roughcut_draft_cleanup_pending()
        
        # 백그라운드 STT/앙상블/옵티마이저 스레드가 아직 일하고 있는지 추가 확인!
        if not is_busy:
            for t in threading.enumerate():
                if t.is_alive() and any(x in t.name.lower() for x in ["stt", "ensemble", "optimizer", "preview"]):
                    is_busy = True
                    break
                    
        if is_busy:
            QTimer.singleShot(500, self._release_ai_models_after_roughcut_draft)
            return
            
        try:
            main_w = self.window()
        except RuntimeError:
            return
        release = getattr(main_w, "_release_ai_models_for_editor_mode", None)
        if callable(release):
            release(force=True, preserve_roughcut_status=True)

    def _post_completion_sync(self):
        """E fix: 자막 생성 완료 후 타임라인/글로벌 캔버스 재동기화"""
        try:
            self._redraw_timeline()
        except Exception:
            pass
        try:
            if hasattr(self, "timeline"):
                boxes = list(getattr(self.timeline.canvas, "_multiclip_boxes", []) or [])
                if boxes:
                    self.timeline.fit_to_view()
                    gc = self.timeline.global_canvas
                    gc.total_duration = self.timeline.canvas.total_duration
                    gc.update()
                    self.timeline.canvas.update()
                else:
                    self.timeline.fit_to_view()
        except Exception:
            pass
        try:
            if hasattr(self, "_resolve_active_context") and hasattr(self, "_apply_active_context"):
                ctx = self._resolve_active_context()
                self._apply_active_context(ctx, autoplay=False, show_thumbnail=True)
        except Exception:
            pass

    def _execute_pipeline_logic(self, is_restart):
        main_w = self.window()
        # 기존 자막이 사전 로드된 상태면 clear하지 않음
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


    def _connect_cut_boundary_placeholder_signal(self):
        """Connect cut-boundary placeholder refresh signal to editor UI bridge."""
        try:
            main_w = self.window()
        except Exception:
            return

        connected = False
        for owner in (main_w, self):
            try:
                sig = getattr(owner, "_sig_refresh_cut_boundary_placeholder", None)
                if sig is None or not hasattr(sig, "connect"):
                    continue
                try:
                    sig.disconnect(self._refresh_cut_boundary_placeholder_from_project)
                except Exception:
                    pass
                sig.connect(self._refresh_cut_boundary_placeholder_from_project)
                connected = True
            except Exception:
                pass

        if connected:
            try:
                QTimer.singleShot(0, self._refresh_cut_boundary_placeholder_from_project)
            except Exception:
                pass

    def _refresh_cut_boundary_placeholder_from_project(self):
        """Load gray topicless middle segments from project and push them to UI objects.

        This must run on the Qt/main thread. Backend cut scanning only saves
        project data and emits a lightweight refresh signal.
        """
        try:
            import threading as _th
            if _th.current_thread() is not _th.main_thread():
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

            from core.roughcut.cut_boundary_placeholder import extract_topicless_placeholders_from_project
            rows = extract_topicless_placeholders_from_project(project_path)
            rows = [dict(row) for row in list(rows or [])]

            # Editor 자체에 반영
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

            # roughcut result 형태로도 반영
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
                }
            for attr in ("_roughcut_result", "roughcut_result", "_roughcut_draft_result"):
                try:
                    setattr(self, attr, dict(result_dict) if isinstance(result_dict, dict) else None)
                except Exception:
                    pass

            # timeline/canvas 쪽에 가능한 이름으로 주입
            timeline = getattr(self, "timeline", None)
            canvas = getattr(timeline, "canvas", None) if timeline is not None else None
            global_canvas = getattr(timeline, "global_canvas", None) if timeline is not None else None

            for obj in (timeline, canvas, global_canvas):
                if obj is None:
                    continue
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
                    obj.update()
                except Exception:
                    pass

            # 존재하는 refresh 계열 메서드 호출
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


    # ---------------------------------------------------------
    # Partial Recognition
    # ---------------------------------------------------------

    def _add_cut_boundary_level_submenu(self, menu):
        try:
            from core.settings import load_settings
            try:
                from core.cut_boundary import cut_boundary_level
            except Exception:
                cut_boundary_level = None

            settings = load_settings() or {}
            current = cut_boundary_level(settings) if callable(cut_boundary_level) else str(settings.get("scan_cut_boundary_level", "medium"))

            sub = menu.addMenu("🎬 컷 경계 단계")
            choices = [
                ("off", "사용안함"),
                ("low", "낮음 - 3초 간격"),
                ("medium", "중간 - 2초 간격"),
            ]

            for level, label in choices:
                act = sub.addAction(label)
                act.setCheckable(True)
                act.setChecked(level == current)
                act.triggered.connect(lambda checked=False, lv=level: self._set_cut_boundary_level_from_menu(lv))
        except Exception as exc:
            try:
                get_logger().log(f"⚠️ 컷 경계 단계 메뉴 생성 실패: {exc}")
            except Exception:
                pass

    def _set_cut_boundary_level_from_menu(self, level: str):
        try:
            from core.settings import load_settings
            try:
                from core.settings import save_settings
            except Exception:
                save_settings = None

            settings = load_settings() or {}
            level = str(level or "medium")
            if level == "high":
                level = "medium"
            settings["scan_cut_boundary_level"] = level
            settings["cut_boundary_level"] = level

            # 기존 boolean 호환
            settings["scan_cut_enabled"] = level != "off"
            settings["scan_cut_auto_enabled"] = level != "off"
            settings["cut_boundary_enabled"] = level != "off"

            # profile label 보조 저장
            labels = {
                "off": "사용안함",
                "low": "낮음 - 3초 간격",
                "medium": "중간 - 2초 간격",
            }
            masks = {
                "off": "off",
                "low": "cross4",
                "medium": "cross5",
            }
            settings["scan_cut_boundary_label"] = labels.get(level, labels["medium"])
            settings["scan_cut_grid_mask"] = masks.get(level, "cross5")

            if callable(save_settings):
                save_settings(settings)
            else:
                # save_settings가 없는 빌드 대비: self.settings에는 즉시 반영
                pass

            if hasattr(self, "settings") and isinstance(self.settings, dict):
                self.settings.update(settings)

            try:
                self.sm.set_custom_status(f"🎬 컷 경계 단계: {settings['scan_cut_boundary_label']}")
            except Exception:
                pass

            try:
                get_logger().log(f"  🎚️ [컷 경계] 단계 변경: {settings['scan_cut_boundary_label']}")
            except Exception:
                pass
        except Exception as exc:
            try:
                get_logger().log(f"⚠️ 컷 경계 단계 저장 실패: {exc}")
            except Exception:
                pass


    def _show_playhead_menu(self, gpos, sec):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { font-size: 13px; }")
        if hasattr(self, "_add_cut_boundary_level_submenu"):
            self._add_cut_boundary_level_submenu(menu)
            menu.addSeparator()
        act_cur = menu.addAction("🎯 현재 자막 세그먼트만 재인식")
        act_end = menu.addAction("🚀 현재부터 끝까지 자막 재인식")
        action = menu.exec(gpos)
        if action == act_cur: self._re_recognize_segment(sec)
        elif action == act_end: self._re_recognize_from(sec)

    def _re_recognize_segment(self, sec):
        segs = self._get_current_segments()
        for s in segs:
            if s["start"] <= sec < s["end"]:
                self._run_partial_backend(s["start"], s["end"], is_single=True)
                break

    def _re_recognize_from(self, sec):
        segs = self._get_current_segments()
        start_sec = sec
        for s in segs:
            if s["start"] <= sec < s["end"]:
                start_sec = s["start"]
                break
        end_sec = self._partial_rerun_total_end()
        self._run_partial_backend(start_sec, end_sec, is_single=False)

    def _partial_rerun_total_end(self) -> float:
        try:
            total = float(getattr(getattr(self, "video_player", None), "total_time", 0.0) or 0.0)
            if total > 0.0:
                return total
        except Exception:
            pass
        try:
            total = float(getattr(getattr(self, "timeline", None), "total_duration", 0.0) or 0.0)
            if total > 0.0:
                return total
        except Exception:
            pass
        segs = list(self._get_current_segments() or [])
        if segs:
            try:
                return max(float(seg.get("end", 0.0) or 0.0) for seg in segs)
            except Exception:
                pass
        return 99999.0

    def _trim_vad_segments_before(self, vad_segments, cutoff_sec: float) -> list[dict]:
        cutoff = max(0.0, float(cutoff_sec or 0.0))
        kept: list[dict] = []
        for seg in list(vad_segments or []):
            if not isinstance(seg, dict):
                continue
            try:
                start = float(seg.get("start", 0.0) or 0.0)
                end = float(seg.get("end", start) or start)
            except Exception:
                continue
            if end <= cutoff:
                kept.append(dict(seg))
                continue
            if start < cutoff < end:
                clipped = dict(seg)
                clipped["start"] = start
                clipped["end"] = cutoff
                kept.append(clipped)
        return kept

    def _trim_cut_boundary_rows_before(self, rows, cutoff_sec: float) -> list[dict]:
        cutoff = max(0.0, float(cutoff_sec or 0.0))
        kept: list[dict] = []
        for row in list(rows or []):
            try:
                if isinstance(row, dict):
                    sec = float(row.get("timeline_sec", row.get("time", row.get("start", 0.0))) or 0.0)
                else:
                    sec = float(row)
            except Exception:
                continue
            if sec < cutoff - 0.0005:
                kept.append(dict(row) if isinstance(row, dict) else sec)
        return kept

    def _trim_cut_boundary_state_for_partial_rerun(self, start_sec: float) -> None:
        main_w = self.window()
        backend = getattr(main_w, "backend", None) if main_w is not None else None
        project_path = str(getattr(main_w, "_current_project_path", "") or "") if main_w is not None else ""
        project_cut_rows = []
        project_provisional_rows = []
        if project_path and os.path.exists(project_path):
            try:
                from core.project.project_io import read_project_file

                project = read_project_file(project_path)
                analysis = project.get("analysis", {}) or {}
                project_cut_rows = list(analysis.get("cut_boundaries", []) or [])
                project_provisional_rows = list(analysis.get("cut_boundary_provisional_boundaries", []) or [])
            except Exception:
                project_cut_rows = []
                project_provisional_rows = []

        prefix_time_rows = self._trim_cut_boundary_rows_before(
            project_cut_rows or (getattr(main_w, "_project_boundary_times", []) if main_w is not None else []),
            start_sec,
        )
        prefix_provisionals = self._trim_cut_boundary_rows_before(
            project_provisional_rows or getattr(self, "_auto_cut_boundary_scan_lines", []),
            start_sec,
        )
        prefix_times = []
        for item in list(prefix_time_rows or []):
            try:
                if isinstance(item, dict):
                    sec = float(item.get("timeline_sec", item.get("time", item.get("start", 0.0))) or 0.0)
                else:
                    sec = float(item)
                prefix_times.append(sec)
            except Exception:
                continue

        if main_w is not None:
            try:
                main_w._project_boundary_times = list(prefix_times)
            except Exception:
                pass
            try:
                if hasattr(main_w, "_sig_update_project_boundary_times"):
                    main_w._sig_update_project_boundary_times.emit(list(prefix_times))
            except Exception:
                pass

        try:
            self._project_boundary_times = list(prefix_times)
        except Exception:
            pass
        try:
            if hasattr(self, "_set_auto_cut_boundary_scan_lines"):
                self._set_auto_cut_boundary_scan_lines(list(prefix_provisionals))
        except Exception:
            pass
        try:
            timeline = getattr(self, "timeline", None)
            if timeline is not None:
                if hasattr(timeline, "set_boundary_times"):
                    timeline.set_boundary_times(list(prefix_times))
                if hasattr(timeline, "set_scan_boundary_times"):
                    timeline.set_scan_boundary_times(list(prefix_provisionals))
        except Exception:
            pass
        if project_path and os.path.exists(project_path):
            try:
                from core.cut_boundary import sync_project_cut_boundaries
                from core.project.project_io import read_project_file, write_project_file

                project = read_project_file(project_path)
                analysis = project.setdefault("analysis", {})
                analysis["cut_boundaries"] = list(prefix_time_rows)
                analysis["cut_boundary_provisional_boundaries"] = list(prefix_provisionals)
                for key in (
                    "cut_boundary_prescan_done",
                    "cut_boundary_cache_path",
                    "cut_boundary_cache_type",
                ):
                    analysis.pop(key, None)
                sync_project_cut_boundaries(
                    project,
                    settings=project.get("user_settings", {}),
                    provisional_boundaries=list(prefix_provisionals),
                )
                write_project_file(project_path, project)
            except Exception as exc:
                get_logger().log(f"⚠️ 부분 재인식 컷 경계 상태 정리 실패: {exc}")

        if backend is not None:
            try:
                backend._cut_boundary_pipeline_cache = None
            except Exception:
                pass
            try:
                backend._cut_boundary_provisional_rows = [dict(item) for item in prefix_provisionals]
            except Exception:
                pass
            try:
                from core.settings import load_settings

                settings = load_settings() or {}
                media_path = str(getattr(self, "media_path", "") or "")
                if media_path and hasattr(backend, "_cut_boundary_cache_path_for_start"):
                    cache_path = backend._cut_boundary_cache_path_for_start([media_path], settings)
                    if cache_path and os.path.exists(cache_path):
                        os.remove(cache_path)
            except Exception:
                pass

        try:
            owner = main_w if main_w is not None else self
            sig = getattr(owner, "_sig_refresh_cut_boundary_placeholder", None)
            if sig is not None and hasattr(sig, "emit"):
                sig.emit()
        except Exception:
            pass

    def _prepare_partial_rerun_state(self, start_sec: float, end_sec: float, *, rerun_cut_boundaries: bool = False) -> list[dict]:
        if hasattr(self, "clear_segments_in_range"):
            self.clear_segments_in_range(start_sec, end_sec)

        live_preview = []
        for seg in list(getattr(self, "_live_stt_preview_segments", []) or []):
            try:
                seg_end = float(seg.get("end", seg.get("start", 0.0)) or 0.0)
            except Exception:
                continue
            if seg_end <= float(start_sec or 0.0):
                live_preview.append(dict(seg))
        self._live_stt_preview_segments = live_preview
        remover = getattr(self, "_remove_live_editor_preview_overlapping", None)
        if callable(remover):
            remover([{"start": float(start_sec or 0.0), "end": float(end_sec or start_sec or 0.0)}])

        existing_vad = []
        try:
            existing_vad = list(getattr(getattr(self.timeline, "canvas", None), "vad_segments", []) or [])
        except Exception:
            existing_vad = []
        prefix_vad = self._trim_vad_segments_before(existing_vad, start_sec)
        try:
            if hasattr(self, "set_vad_segments"):
                self.set_vad_segments(list(prefix_vad))
        except Exception:
            pass

        if rerun_cut_boundaries:
            self._trim_cut_boundary_state_for_partial_rerun(start_sec)
        return prefix_vad

    def _update_partial_progress(self, sec):
        if hasattr(self, 'timeline') and hasattr(self.timeline, 'canvas'):
            self.timeline.canvas.re_recog_progress = sec
            self.timeline.canvas.update()

    def _run_partial_backend(self, start_sec, end_sec, is_single=False):
        main_w = self.window()
        if not (main_w and main_w.backend): return
        if is_single: self.sm.start_partial_segment()
        else: self.sm.start_partial_from_here()
        rerun_cut_boundaries = not bool(is_single)
        prefix_vad = self._prepare_partial_rerun_state(
            start_sec,
            end_sec,
            rerun_cut_boundaries=rerun_cut_boundaries,
        )
        if hasattr(self, 'timeline') and hasattr(self.timeline, 'canvas'):
            self.timeline.canvas.re_recog_zone = (start_sec, end_sec)
            self.timeline.canvas.re_recog_progress = start_sec
            self.timeline.canvas.update()
        self._partial_signals = PartialSignals()
        self._partial_signals.status.connect(lambda _code, msg: self.update_status(msg))
        self._partial_signals.progress.connect(self.update_progress)
        self._partial_signals.chunk_time.connect(self._update_partial_progress)
        if hasattr(self, 'insert_partial_segments'):
            self._partial_signals.done.connect(self.insert_partial_segments)
        def on_finished():
            if hasattr(self, '_spinner_timer'): self._spinner_timer.stop()
            self.sm.complete_ai()
            if hasattr(self, 'timeline') and hasattr(self.timeline, 'canvas'):
                self.timeline.canvas.re_recog_zone = None
                self.timeline.canvas.re_recog_progress = None
                self.timeline.canvas.update()
            try:
                if hasattr(main_w, "_sig_set_llm_review_segment"):
                    main_w._sig_set_llm_review_segment.emit({"active": False})
            except Exception:
                pass
        self._partial_signals.finished.connect(on_finished)
        def _task():
            sig = self._partial_signals
            backend = getattr(main_w, "backend", None)
            if backend is None:
                sig.finished.emit()
                return
            try:
                media_path = str(getattr(self, "media_path", "") or "")
                project_path = str(getattr(main_w, "_current_project_path", "") or "")
                if rerun_cut_boundaries and media_path and project_path:
                    sig.status.emit("STATUS_CUT_BOUNDARY", "컷 경계 다시 분석 중...")
                    try:
                        backend._auto_scan_cut_boundaries_for_start_sync(project_path, [media_path])
                        follower = getattr(backend, "_cut_boundary_follower_thread", None)
                        if follower is not None and follower.is_alive():
                            follower.join()
                    except Exception as exc:
                        get_logger().log(f"⚠️ 부분 재인식 컷 경계 재분석 실패: {exc}")

                cut_boundary_snapshot = (
                    backend._cut_boundary_snapshot_for_pipeline(force_reload=True)
                    if hasattr(backend, "_cut_boundary_snapshot_for_pipeline")
                    else {"cut_boundaries": [], "provisional_cut_boundaries": []}
                )
                pipeline_cut_boundaries = [
                    dict(row) for row in list(cut_boundary_snapshot.get("cut_boundaries", []) or [])
                ]
                pipeline_provisional_cut_boundaries = [
                    dict(row) for row in list(cut_boundary_snapshot.get("provisional_cut_boundaries", []) or [])
                ]

                try:
                    from core.frame_time import sec_to_frame, frame_to_sec

                    hard_cuts = []
                    for row in pipeline_cut_boundaries:
                        try:
                            fps = float(row.get("fps", row.get("timeline_frame_rate", row.get("frame_rate", 30.0))) or 30.0)
                            frame = row.get("timeline_frame", row.get("frame"))
                            if frame is None:
                                frame = sec_to_frame(float(row.get("timeline_sec", row.get("time", 0.0)) or 0.0), fps)
                            sec = frame_to_sec(int(frame), fps)
                            if sec > 0.0:
                                hard_cuts.append(round(sec, 3))
                        except Exception:
                            continue
                    backend.video_processor.hard_cut_boundaries = sorted(set(hard_cuts))
                except Exception as exc:
                    get_logger().log(f"⚠️ 부분 재인식 hard cut 적용 실패: {exc}")

                sig.status.emit("STATUS_PREPARING_AUDIO", "오디오 추출 및 정제 중...")
                if hasattr(backend, "video_processor"):
                    backend.video_processor.stage_callback = lambda status: sig.status.emit("STATUS_STAGE", status)

                chunk_dir, vad_segs = backend.video_processor.extract_audio(
                    media_path,
                    target_start_sec=start_sec,
                    target_end_sec=end_sec,
                    is_single_segment=is_single,
                )
                merged_vad = list(prefix_vad) + list(vad_segs or [])
                if hasattr(self, "set_vad_segments"):
                    QTimer.singleShot(0, lambda segs=list(merged_vad): self.set_vad_segments(segs))

                from core.engine.subtitle_engine import apply_final_gap_settings, optimize_segments
                from core.engine.subtitle_timing import align_stt_candidates_to_subtitle_segments
                from core.pipeline.stt_preview_optimizer import optimize_stt_preview_segments

                opt_queue = queue.Queue()
                preview_opt_queue = queue.Queue()
                preview_opt_sentinel = object()
                opt_sentinel = object()
                auto_collected_segs = []

                audio_for_diarization = media_path
                try:
                    base_name = os.path.splitext(os.path.basename(media_path))[0]
                    cleaned_wav = str(getattr(backend.video_processor, "last_cleaned_wav", "") or "")
                    raw_wav = str(getattr(backend.video_processor, "last_raw_wav", "") or "")
                    if (not cleaned_wav or not os.path.exists(cleaned_wav)) and hasattr(backend.video_processor, "_audio_work_paths"):
                        try:
                            audio_paths = backend.video_processor._audio_work_paths(media_path)
                            cleaned_wav = str(audio_paths.get("cleaned_wav") or cleaned_wav)
                            raw_wav = str(audio_paths.get("raw_wav") or raw_wav)
                        except Exception:
                            pass
                    if not cleaned_wav:
                        cleaned_wav = os.path.join(config.OUTPUT_DIR, f"{base_name}_cleaned.wav")
                    if not raw_wav:
                        raw_wav = os.path.join(config.OUTPUT_DIR, f"{base_name}.wav")
                    if os.path.exists(cleaned_wav):
                        audio_for_diarization = cleaned_wav
                    elif os.path.exists(raw_wav):
                        audio_for_diarization = raw_wav
                except Exception:
                    pass

                t_diarize = None
                if getattr(backend, "max_speakers", 1) > 1 and hasattr(backend, "_prepare_speaker_map"):
                    t_diarize = threading.Thread(
                        target=backend._prepare_speaker_map,
                        args=(audio_for_diarization,),
                        daemon=True,
                        name="partial-diarizer",
                    )
                    t_diarize.start()

                def _emit_processed_preview(chunk_segs, label="STT"):
                    preview = optimize_stt_preview_segments(
                        chunk_segs,
                        source_label=str(label or "STT"),
                        vad_segments=merged_vad,
                        cut_boundaries=pipeline_cut_boundaries,
                        provisional_cut_boundaries=pipeline_provisional_cut_boundaries,
                    )
                    if preview and hasattr(main_w, "_sig_preview_stt_segments"):
                        main_w._sig_preview_stt_segments.emit(preview)

                def _preview_stt_segments(chunk_segs, label="STT"):
                    if not chunk_segs:
                        return
                    preview_opt_queue.put(([dict(seg) for seg in chunk_segs or []], str(label or "STT")))

                def do_preview_optimize():
                    while True:
                        item = preview_opt_queue.get()
                        if item is preview_opt_sentinel:
                            break
                        try:
                            chunk_segs, label = item
                            _emit_processed_preview(chunk_segs, label)
                        except Exception as exc:
                            get_logger().log(f"⚠️ 부분 재인식 STT 후보 자막 후처리 오류: {exc}")

                def do_transcribe():
                    try:
                        for chunk, idx, total in backend.video_processor.transcribe(
                            chunk_dir,
                            is_fast_mode=False,
                            target_end_sec=end_sec,
                            is_single=is_single,
                            preview_callback=_preview_stt_segments,
                        ):
                            opt_queue.put((chunk, idx, total))
                    finally:
                        preview_opt_queue.put(preview_opt_sentinel)
                        opt_queue.put(opt_sentinel)

                def _flush_buffer(seg_buffer, last_c_idx, last_t_total):
                    if not seg_buffer:
                        return []
                    chunk_segs = list(seg_buffer)
                    try:
                        def _llm_progress(payload):
                            if hasattr(main_w, "_sig_set_llm_review_segment"):
                                main_w._sig_set_llm_review_segment.emit(dict(payload or {}))

                        sig.status.emit("STATUS_LLM", "자막 LLM 교정/분리 중...")
                        opt = optimize_segments(
                            chunk_segs,
                            vad_segments=merged_vad,
                            llm_progress_callback=_llm_progress,
                        )
                    except Exception as exc:
                        get_logger().log(f"⚠️ 부분 재인식 LLM 최적화 실패, STT 결과 유지: {exc}")
                        opt = chunk_segs
                    finally:
                        try:
                            if hasattr(main_w, "_sig_set_llm_review_segment"):
                                main_w._sig_set_llm_review_segment.emit({"active": False})
                        except Exception:
                            pass

                    for seg in opt:
                        if seg["start"] < 0.0:
                            seg["start"] = 0.0
                        if seg["end"] <= seg["start"]:
                            seg["end"] = seg["start"] + 0.5

                    if hasattr(backend, "_magnetize_by_saved_cut_boundaries"):
                        opt = backend._magnetize_by_saved_cut_boundaries(
                            opt,
                            context="부분 재인식 정식 컷",
                            include_provisional=False,
                        )
                    if hasattr(backend, "_split_by_saved_cut_boundaries"):
                        opt = backend._split_by_saved_cut_boundaries(opt, context="부분 재인식 자막")
                    if hasattr(backend, "_align_subtitle_segments_to_vad"):
                        opt = backend._align_subtitle_segments_to_vad(
                            opt,
                            merged_vad,
                            context="부분 재인식",
                        )

                    if getattr(backend, "max_speakers", 1) > 1 and getattr(backend, "_speaker_map", None):
                        try:
                            from core.audio.diarize import get_speaker_for_segment

                            for seg in opt:
                                spk_full = get_speaker_for_segment(
                                    seg["start"], seg["end"], backend._speaker_map
                                )
                                seg["speaker"] = spk_full.replace("SPEAKER_", "")
                        except Exception:
                            pass

                    opt = apply_final_gap_settings(opt, force=True)
                    if hasattr(backend, "_magnetize_by_saved_cut_boundaries"):
                        opt = backend._magnetize_by_saved_cut_boundaries(
                            opt,
                            context="부분 재인식 임시 컷",
                            include_confirmed=False,
                            include_provisional=True,
                        )
                    if hasattr(backend, "_split_by_saved_cut_boundaries"):
                        opt = backend._split_by_saved_cut_boundaries(opt, context="부분 재인식 자막")
                    opt = align_stt_candidates_to_subtitle_segments(opt)
                    auto_collected_segs.extend([dict(seg) for seg in opt])

                    sig.status.emit("STATUS_INSERTING_SEGS", "자막 정밀 삽입 중...")
                    sig.done.emit(opt)
                    sig.progress.emit(last_c_idx, last_t_total)
                    if auto_collected_segs:
                        try:
                            sig.chunk_time.emit(float(auto_collected_segs[-1].get("end", start_sec) or start_sec))
                        except Exception:
                            pass
                    return []

                def do_optimize():
                    if t_diarize and t_diarize.is_alive():
                        try:
                            t_diarize.join()
                        except Exception:
                            pass

                    seg_buffer = []
                    last_c_idx = 0
                    last_t_total = 1

                    while True:
                        item = opt_queue.get()
                        if item is opt_sentinel:
                            _flush_buffer(seg_buffer, last_c_idx, last_t_total)
                            break

                        chunk_segs, c_idx, t_total = item
                        last_c_idx = c_idx
                        last_t_total = t_total
                        sig.progress.emit(c_idx, t_total)

                        if not chunk_segs:
                            continue
                        try:
                            sig.status.emit("STATUS_TRANSCRIBING", f"Whisper 자막 인식 중 ({c_idx}/{t_total})")
                            sig.chunk_time.emit(float(chunk_segs[-1].get("end", start_sec) or start_sec))
                        except Exception:
                            pass
                        seg_buffer.extend(chunk_segs)
                        seg_buffer = _flush_buffer(seg_buffer, last_c_idx, last_t_total)

                t_preview = threading.Thread(target=do_preview_optimize, daemon=True, name="partial-preview-opt")
                t_trans = threading.Thread(target=do_transcribe, daemon=True, name="partial-transcriber")
                t_opt = threading.Thread(target=do_optimize, daemon=True, name="partial-optimizer")
                t_preview.start()
                t_trans.start()
                t_opt.start()
                t_trans.join()
                t_preview.join()
                t_opt.join()
            except Exception as e:
                get_logger().log(f"⚠️ 재인식 중 치명적 오류: {e}")
            finally:
                try:
                    if hasattr(backend, "video_processor"):
                        backend.video_processor.stage_callback = None
                except Exception:
                    pass
            sig.finished.emit()
        threading.Thread(target=_task, daemon=True).start()

    # ---------------------------------------------------------
    # Progress & Status
    # ---------------------------------------------------------
    def set_live_processing_stage(self, text: str):
        import threading as _th
        if _th.current_thread() is not _th.main_thread():
            QTimer.singleShot(0, lambda t=str(text or ""): self.set_live_processing_stage(t))
            return
        message = str(text or "").strip()
        if not message:
            return
        now = time.monotonic()
        if (
            message == str(getattr(self, "_last_live_processing_stage", "") or "")
            and now < float(getattr(self, "_next_live_processing_stage_at", 0.0) or 0.0)
        ):
            return
        self._last_live_processing_stage = message
        self._next_live_processing_stage_at = now + 0.25
        try:
            if hasattr(self, "sm") and getattr(self.sm, "is_locked", False):
                self.sm.set_custom_status(message)
            elif hasattr(self, "status_lbl"):
                self.status_lbl.setText(message)
        except RuntimeError:
            return

    # ✅ [v01.00.16] 완료 조건 단일화 — EditorPipeline만 완료 판단
    def update_progress(self, c_idx, t_total):
        import threading as _th
        if _th.current_thread() is not _th.main_thread():
            QTimer.singleShot(0, lambda c=c_idx, t=t_total: self.update_progress(c, t))
            return

        total_vid_time = getattr(self.video_player, 'total_time', 0.0) if hasattr(self, 'video_player') else 0.0
        segs = self._get_current_segments()
        current_end = segs[-1].get('end', 0.0) if segs else 0.0

        if total_vid_time > 0 and current_end > 0:
            pct = min(100, int((current_end / total_vid_time) * 100))
        elif t_total > 0:
            pct = min(100, int((c_idx / t_total) * 100))
        else:
            pct = 0

        self.sm.update_progress(c_idx, t_total, pct)

        # ✅ 완료 조건 단일화
        if t_total > 0 and c_idx >= t_total and not getattr(self, '_completion_handled', False):
            self._completion_handled = True
            QTimer.singleShot(0, self._set_process_completed)

    def update_status(self, text, is_final=False, is_raw=False):
        import threading as _th
        if _th.current_thread() is not _th.main_thread():
            QTimer.singleShot(0, lambda t=text, f=is_final, r=is_raw: self.update_status(t, f, r))
            return
        if is_final or "에러" in text or "실패" in text:
            if "완료" in text: self.sm.complete_ai()
            else: self.sm.stop_processing(text)
            if hasattr(self, '_spinner_timer'): self._spinner_timer.stop()
        else:
            self.sm.set_custom_status(text)
