# Version: 03.08.10
# Phase: PHASE2
"""
ui/editor_actions.py
에디터 UI 버튼 액션 (저장/이전/종료/내보내기/설정)
- editor_pipeline.py에서 분리
"""

import hashlib
import json
import os
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import Qt

import config
from logger import get_logger
from core.project.data_manager import save_settings as _dm_save_settings
from core.engine.subtitle_engine import save_srt
from core.path_manager import get_srt_path
from core.work_mode import EDITOR_MODE, normalize_work_mode
from ui.dialogs.message_box import confirm_save_changes


class EditorActionsMixin:
    """저장 / 이전 / 종료 / 내보내기 / 설정 다이얼로그"""

    # ---------------------------------------------------------
    # 공통 유틸
    # ---------------------------------------------------------
    def _go_home(self):
        try:
            self._cleanup()
        except Exception:
            pass
        try:
            self.sig_prev.emit()
        except Exception:
            pass
        try:
            main_w = self.window()
            for name in ("handle_prev", "show_home", "go_home", "_show_home", "show_main"):
                if hasattr(main_w, name) and callable(getattr(main_w, name)):
                    getattr(main_w, name)()
                    break
        except Exception:
            pass

    def _show_confirm_dialog(self, title, text):
        return confirm_save_changes(self, title=title)

    # ---------------------------------------------------------
    # 저장
    # ---------------------------------------------------------
    def _segments_dirty_signature(self, segs: list | None = None) -> str:
        if segs is None:
            segs = self._get_current_segments()
        normalized = []
        for seg in list(segs or []):
            normalized.append(
                {
                    "start": round(float(seg.get("start", 0.0) or 0.0), 3),
                    "end": round(float(seg.get("end", seg.get("start", 0.0)) or 0.0), 3),
                    "text": str(seg.get("text", "") or ""),
                    "speaker": str(seg.get("speaker", seg.get("spk", "")) or ""),
                    "is_gap": bool(seg.get("is_gap", False)),
                    "stt_pending": bool(seg.get("stt_pending", False)),
                    "stt_mode": bool(seg.get("stt_mode", False)),
                }
            )
        payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _remember_saved_segments(self, segs: list | None = None):
        try:
            self._saved_segments_signature = self._segments_dirty_signature(segs)
        except Exception:
            self._saved_segments_signature = ""

    def _has_unsaved_changes(self) -> bool:
        saved_sig = getattr(self, "_saved_segments_signature", None)
        if saved_sig:
            try:
                return self._segments_dirty_signature() != saved_sig
            except Exception:
                pass
        try:
            return bool(getattr(self.sm, "is_dirty", False))
        except Exception:
            return bool(getattr(self, "_is_dirty", False))

    def _mark_save_completed(self, touch_saved_time: bool = True) -> bool:
        try:
            if hasattr(self, "sm"):
                if getattr(self.sm, "is_locked", False):
                    self.sm.is_dirty = False
                    if hasattr(self.sm, "_broadcast"):
                        self.sm._broadcast()
                else:
                    self.sm.complete_save()
        except Exception:
            pass

        try:
            main_w = self.window()
            if hasattr(main_w, "_refresh_saved_status_label"):
                main_w._refresh_saved_status_label(is_dirty=False, touch_saved_time=touch_saved_time)
        except Exception:
            pass
        return True

    def _flush_pending_segment_queue_now(self):
        try:
            timer = getattr(self, "_queue_timer", None)
            if timer is not None and hasattr(timer, "isActive") and timer.isActive():
                timer.stop()
        except Exception:
            pass
        try:
            queue = list(getattr(self, "_segment_queue", []) or [])
            if queue and hasattr(self, "_flush_queue"):
                self._flush_queue()
        except Exception:
            pass

    def _segments_for_srt_output(self, segs: list[dict]) -> list[dict]:
        """Return SRT output order; currently changes only when roughcut explicitly enables it."""
        try:
            main_w = self.window()
            project_path = str(getattr(main_w, "_current_project_path", "") or "")
            if not project_path or not os.path.exists(project_path):
                return list(segs or [])
            from core.project.project_manager import load_project
            from core.roughcut import apply_roughcut_order_to_subtitles

            project = load_project(project_path) or {}
            ordered = apply_roughcut_order_to_subtitles(list(segs or []), project.get("roughcut_state", {}) or {})
            if ordered != list(segs or []):
                get_logger().log("러프컷 편집 순서를 SRT 저장 순서에 반영했습니다.")
            return ordered
        except Exception:
            return list(segs or [])

    def _on_save(self, *args, skip_auto_next=False):
        self._flush_pending_segment_queue_now()
        segs = self._get_current_segments()
        if not segs:
            get_logger().log("💾 저장 취소: 저장할 자막 세그먼트가 없습니다.")
            return False
        if hasattr(self, "_warn_pending_stt_before_save") and not self._warn_pending_stt_before_save(segs):
            get_logger().log("💾 저장 취소: STT 미완료 세그먼트 확인 필요")
            return False

        try:
            main_w = self.window()
            multiclip_files = list(getattr(main_w, '_multiclip_files', []) or [])
            srt_output_segs = self._segments_for_srt_output(segs)
            saved_any = False
            if len(multiclip_files) > 1:
                saved_any = self._save_multiclip_srts(srt_output_segs, multiclip_files)
            elif getattr(self, 'media_path', None):
                srt_path = get_srt_path(self.media_path)
                save_srt(srt_output_segs, srt_path)
                get_logger().log(f"💾 저장 완료: {os.path.basename(srt_path)}")
                saved_any = True
            else:
                get_logger().log("⚠️ 저장 실패: media_path가 없어 SRT 저장 경로를 만들 수 없습니다.")
                return False
            if not saved_any:
                get_logger().log("⚠️ 저장 실패: 실제로 저장된 자막 파일이 없습니다.")
                return False
        except Exception as e:
            get_logger().log(f"⚠️ 저장 실패: {e}")
            return False

        try:
            self.sig_save.emit(segs)
        except Exception:
            pass

        self._remember_saved_segments(segs)
        self._mark_save_completed(touch_saved_time=True)

        if not skip_auto_next:
            self._skip_prev_confirm_once = True

        try:
            self._auto_save_project(segs)
        except Exception as e:
            get_logger().log(f"⚠️ 프로젝트 자동 저장 실패: {e}")
        return True

    # ---------------------------------------------------------
    # 멀티클립 SRT 저장 (개별 + 통합)
    # ---------------------------------------------------------
    def _save_multiclip_srts(self, segs, multiclip_files):
        """멀티클립 자막을 개별 SRT + 통합 SRT로 저장합니다."""
        main_w = self.window()

        # boundaries 탐색: self → main_w → timeline canvas boxes
        boundaries = (
            getattr(self, '_multiclip_boundaries', None)
            or getattr(main_w, '_multiclip_boundaries', None)
            or (getattr(self.timeline.canvas, '_multiclip_boxes', None)
                if hasattr(self, 'timeline') else None)
            or []
        )

        # reuse indices 탐색: self → main_w
        reuse_indices = (
            getattr(self, '_reuse_clip_indices', None)
            or getattr(main_w, '_reuse_clip_indices', None)
            or set()
        )

        if not boundaries:
            get_logger().log("⚠️ 멀티클립 boundaries 없음 — 단일 파일 저장으로 대체")
            if getattr(self, "media_path", None):
                srt_path = get_srt_path(self.media_path)
                non_gap = [s for s in segs if not s.get("is_gap") and s.get("text", "").strip()]
                save_srt(non_gap, srt_path)
                get_logger().log(f"💾 저장 완료: {os.path.basename(srt_path)}")
                return True
            return False

        def _clip_idx_for(start_sec):
            """세그먼트 시작 시간으로 클립 인덱스 판별"""
            for i, bd in enumerate(boundaries):
                if bd["start"] <= start_sec < bd["end"]:
                    return i
            # 마지막 클립 끝 이후 → 마지막 클립 소속
            if boundaries and start_sec >= boundaries[-1]["start"]:
                return len(boundaries) - 1
            return 0

        def _seg_clip_idx(seg):
            try:
                idx = seg.get("_clip_idx")
                if idx is not None:
                    idx = int(idx)
                    if 0 <= idx < len(boundaries):
                        return idx
            except Exception:
                pass
            return _clip_idx_for(float(seg.get("start", 0.0)))

        # 세그먼트를 clip_idx별로 분류 (boundaries 기반)
        clip_segs = {}
        for seg in segs:
            if seg.get("is_gap") or not seg.get("text", "").strip():
                continue
            cidx = _seg_clip_idx(seg)
            clip_segs.setdefault(cidx, []).append(seg)

        saved_count = 0

        # 개별 SRT 저장 (클립 로컬 타임스탬프)
        for i, clip_file in enumerate(multiclip_files):
            if i in reuse_indices:
                continue  # G fix: skip reuse clips — prevent subtitle duplication
            srt_path = get_srt_path(clip_file)
            c_segs = clip_segs.get(i, [])
            if not c_segs:
                continue

            offset = 0.0
            if i < len(boundaries):
                offset = boundaries[i].get("start", 0.0)

            local_segs = []
            for seg in c_segs:
                ls = dict(seg)
                ls["start"] = max(0.0, float(ls["start"]) - offset)
                ls["end"] = max(0.0, float(ls["end"]) - offset)
                local_segs.append(ls)

            save_srt(local_segs, srt_path)
            saved_count += 1
            get_logger().log(
                f"💾 개별 저장: {os.path.basename(srt_path)} ({len(local_segs)}개)"
            )

        # 통합 SRT 저장 (글로벌 타임스탬프, 기존자막 클립 제외)
        project_path = getattr(main_w, '_current_project_path', None)
        if project_path:
            proj_name = os.path.splitext(os.path.basename(project_path))[0]
        else:
            proj_name = os.path.splitext(os.path.basename(multiclip_files[0]))[0]

        proj_dir = os.path.dirname(multiclip_files[0])
        combined_srt_path = os.path.join(proj_dir, f"{proj_name}_통합.srt")

        combined_segs = []
        for seg in segs:
            if seg.get("is_gap") or not seg.get("text", "").strip():
                continue
            cidx = _seg_clip_idx(seg)
            if cidx in reuse_indices:
                continue
            combined_segs.append(seg)

        combined_segs.sort(key=lambda s: float(s.get("start", 0.0)))

        combined_saved = False
        if combined_segs:
            save_srt(combined_segs, combined_srt_path)
            combined_saved = True
            get_logger().log(
                f"💾 통합 저장: {os.path.basename(combined_srt_path)} "
                f"({len(combined_segs)}개, 기존자막 {len(reuse_indices)}클립 제외)"
            )
        elif segs:
            non_gap = [s for s in segs if not s.get("is_gap") and s.get("text", "").strip()]
            save_srt(non_gap, combined_srt_path)
            combined_saved = True
            get_logger().log(
                f"💾 통합 저장: {os.path.basename(combined_srt_path)} "
                f"({len(non_gap)}개, 전체 포함)"
            )

        get_logger().log(f"✅ 멀티클립 저장 완료: 개별 {saved_count}개 + 통합 1개")
        return bool(saved_count or combined_saved)

    # ---------------------------------------------------------
    # 프로젝트 자동 저장
    # ---------------------------------------------------------
    def _auto_save_project(self, segs: list = None):
        from core.project.project_manager import (
            save_project, create_project, load_project,
            ensure_projects_dir, PROJECTS_DIR
        )

        media_path = getattr(self, 'media_path', None)
        if not media_path:
            return

        main_w = self.window()
        project_path = getattr(main_w, '_current_project_path', None)

        if not project_path:
            base_name = os.path.splitext(os.path.basename(media_path))[0]
            project_path = create_project(
                name=base_name,
                media_paths=[media_path],
                srt_path=get_srt_path(media_path),
                user_settings=dict(getattr(self, "settings", {}) or {}),
            )
            main_w._current_project_path = project_path
            get_logger().log(f"📝 프로젝트 자동 생성: {os.path.basename(project_path)}")

        workspace = {}
        if hasattr(self, 'video_player'):
            workspace["last_playhead"] = getattr(self.video_player, 'current_time', 0.0)
        if hasattr(self, 'text_edit'):
            workspace["last_cursor_block"] = self.text_edit.textCursor().blockNumber()
        if hasattr(self, 'timeline') and hasattr(self.timeline, 'canvas'):
            workspace["zoom_pps"] = self.timeline.canvas.pps
        if hasattr(self, 'splitter'):
            workspace["splitter_sizes"] = self.splitter.sizes()
        try:
            workspace["terminal_visible"] = main_w._log_visible
        except Exception:
            pass
        workspace["dashboard_mode"] = getattr(main_w, "_dashboard_mode", "dashboard") or "dashboard"
        workspace["project_panel_visible"] = bool(getattr(main_w, "_project_panel_visible", True))

        _media_paths = list(getattr(main_w, '_multiclip_files', []) or [])
        if not _media_paths:
            _media_paths = [media_path]
        workspace['selected_segment_line'] = workspace.get('last_cursor_block', 0)
        try:
            workspace['edit_lock'] = bool(self.timeline.lock_chk.isChecked())
        except Exception:
            workspace['edit_lock'] = False
        try:
            workspace['scroll_x'] = int(self.timeline.scroll.horizontalScrollBar().value())
        except Exception:
            workspace['scroll_x'] = 0
        workspace['active_clip_idx'] = int(getattr(self.timeline.canvas, '_active_clip_idx', getattr(main_w, '_active_clip_idx', 0)) or 0)
        workspace['active_work_mode'] = normalize_work_mode(getattr(main_w, '_current_work_mode', EDITOR_MODE))
        save_project(
            filepath=project_path,
            media_paths=_media_paths,
            srt_path=get_srt_path(media_path),
            segments=segs,
            user_settings=dict(getattr(self, "settings", {}) or {}),
            workspace=workspace,
            active_work_mode=workspace['active_work_mode'],
        )
        from core.project.project_phase1b import enrich_existing_project_file
        _owner = locals().get('main_w', self.window() if hasattr(self, 'window') else self)
        _media_path = getattr(self, 'media_path', '') or ''
        _srt_path = ''
        if _media_path:
            _srt_path = os.path.splitext(_media_path)[0] + '.srt'
        enrich_existing_project_file(project_path, _owner, self, segs, _srt_path or None)
        get_logger().log(f"📦 프로젝트 저장 완료: {os.path.basename(project_path)}")

    # ---------------------------------------------------------
    # 이전
    # ---------------------------------------------------------
    def _on_prev(self):
        from core.state_manager import SubtitleStateManager

        if self.sm.state == SubtitleStateManager.ST_PROC:
            self._stop_pipeline()

        if getattr(self, "_skip_prev_confirm_once", False):
            self._skip_prev_confirm_once = False
            self._go_home()
            return

        is_dirty = False
        try:
            is_dirty = self._has_unsaved_changes()
        except Exception:
            pass

        if not is_dirty:
            self._go_home()
            return

        reply = self._show_confirm_dialog(
            "이전으로 이동",
            "저장되지 않은 변경사항이 있습니다.\n저장하시겠습니까?"
        )
        if reply == QMessageBox.StandardButton.Cancel:
            return
        if reply == QMessageBox.StandardButton.Yes:
            if not self._on_save():
                return

        self._go_home()

    # ---------------------------------------------------------
    # 종료
    # ---------------------------------------------------------
    def _on_exit(self):
        from core.state_manager import SubtitleStateManager

        def _emit_exit():
            try:
                self.sig_exit.emit(self._get_current_segments())
            except Exception:
                self.sig_exit.emit([])

        if self.sm.state == SubtitleStateManager.ST_PROC:
            self._stop_pipeline()

        if getattr(self, "_skip_prev_confirm_once", False):
            self._skip_prev_confirm_once = False
            _emit_exit()
            return

        is_dirty = False
        try:
            is_dirty = self._has_unsaved_changes()
        except Exception:
            pass

        if not is_dirty:
            _emit_exit()
            return

        reply = self._show_confirm_dialog(
            "종료",
            "저장되지 않은 변경사항이 있습니다.\n저장하시겠습니까?"
        )
        if reply == QMessageBox.StandardButton.Cancel:
            return
        if reply == QMessageBox.StandardButton.Yes:
            if not self._on_save():
                return

        _emit_exit()

    # ---------------------------------------------------------
    # 다음
    # ---------------------------------------------------------
    def _on_next(self):
        QMessageBox.information(self, "알림", "개발중입니다.")

    # ---------------------------------------------------------
    # 내보내기
    # ---------------------------------------------------------
    def _show_export_dialog(self):
        is_dirty = False
        try:
            if hasattr(self, "sm"):
                is_dirty = self._has_unsaved_changes()
        except Exception:
            pass

        if is_dirty:
            reply = self._show_confirm_dialog(
                "자막 출력",
                "변경된 자막이 저장되지 않았습니다.\n저장 후 출력하시겠습니까?"
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            if reply == QMessageBox.StandardButton.Yes:
                if not self._on_save(skip_auto_next=True):
                    return
                try:
                    is_dirty = self._has_unsaved_changes()
                except Exception:
                    is_dirty = False

        from ui.dialogs.export_dialog import ExportDialog
        segs = self._get_current_segments()
        if segs:
            dlg = ExportDialog(segs, getattr(self, 'video_name', ''), self)
            if hasattr(self, 'video_player'):
                dlg._video_player_ref = self.video_player
            dlg.exec()

    # ---------------------------------------------------------
    # 설정 다이얼로그
    # ---------------------------------------------------------
    def _show_settings(self):
        from ui.settings.settings_dialog import SettingsDialog
        # macOS Qt crash 회피: editor widget setCursor/unsetCursor 금지
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec():
            self.settings = dlg.result_settings
            _dm_save_settings(self.settings)
            self.selected_model = self.settings.get("selected_model", getattr(config, "OLLAMA_MODEL", "exaone3.5:7.8b"))
            if hasattr(self, '_update_engine_label_text'):
                self._update_engine_label_text()
            main_w = self.window()
            if hasattr(main_w, "_refresh_sidebar_engine_info"):
                engine_label = getattr(self, "engine_lbl", None)
                main_w._refresh_sidebar_engine_info(engine_label.text() if engine_label is not None else None)
    def _show_adv_settings(self):
        from ui.settings.settings_dialog import AdvancedSettingsDialog
        dlg = AdvancedSettingsDialog(self.settings, self)
        if dlg.exec():
            self.settings.update(dlg.result)
            _dm_save_settings(self.settings)

    def _show_speaker_settings(self):
        from ui.settings.settings_dialog import SpeakerDialog
        dlg = SpeakerDialog(self.settings, self)
        if dlg.exec():
            self.settings.update(dlg.result)
            _dm_save_settings(self.settings)
            if hasattr(self, '_update_highlighter_colors'):
                self._update_highlighter_colors()
            if hasattr(self, '_refresh_speaker_strip'):
                self._refresh_speaker_strip()

    def _show_gap_settings(self):
        from ui.settings.settings_dialog import GapSettingsDialog
        dlg = GapSettingsDialog(self.settings, self)
        if dlg.exec():
            self.settings.update(dlg.result)
            _dm_save_settings(self.settings)
