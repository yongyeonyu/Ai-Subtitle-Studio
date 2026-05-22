# Version: 03.14.31
# Phase: PHASE2
"""
ui/editor/editor_save_manager.py
자막/프로젝트 저장, 자동저장, dirty 상태, 종료 전 저장 확인,
백업 저장, 캐쉬 삭제 관련 기능을 한 곳에 모은 저장 전용 매니저.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import tempfile
import threading
from typing import Any

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox

from core.engine.subtitle_engine import save_srt
from core.native_swift_timeline import capture_undo_snapshot_via_swift
from core.path_manager import get_srt_path
from core.project.project_runtime_capture import collect_editor_project_aux_state
from core.runtime import config
from core.runtime.logger import get_logger
from core.work_mode import EDITOR_MODE, normalize_work_mode
from ui.dialogs.message_box import confirm_save_changes
from ui.queue.queue_dispatch import find_queue_row_for_media, sync_saved_queue_state
from ui.project.project_session_runtime import attach_project_session


DEFAULT_EDITOR_AUTO_SAVE_INTERVAL_SEC = 300
DEFAULT_PROJECT_ANALYSIS_REFRESH_DELAY_MS = 12_000
DEFAULT_DEFERRED_EDITOR_LEARNING_HOLD_MS = 600_000


def reusable_cache_paths() -> list[str]:
    output_dir = os.path.abspath(str(config.OUTPUT_DIR or ""))
    cache_paths = [
        os.path.join(output_dir, ".media_probe_cache"),
        os.path.join(output_dir, "cut_boundary_cache"),
        os.path.join(output_dir, "waveform_cache"),
        os.path.join(output_dir, "_analysis_cache"),
        os.path.join(output_dir, "_audio_fingerprint"),
        os.path.join(tempfile.gettempdir(), "ai_subtitle_studio_waveform_cache"),
        os.path.join(tempfile.gettempdir(), "ai_subtitle_studio_roughcut"),
        os.path.join(tempfile.gettempdir(), "ai_subtitle_studio_roughcut_thumbnails"),
    ]
    for pattern in (
        "*_cleaned.wav",
        "*_cleaned.wav.meta.json",
        "*_raw.wav",
        "*.vad.cache.json",
        "*.vad.cache.json.gz",
    ):
        cache_paths.extend(glob.glob(os.path.join(output_dir, pattern)))
    deduped: list[str] = []
    seen: set[str] = set()
    for path in cache_paths:
        normalized = os.path.abspath(os.path.expanduser(str(path or "")))
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def clear_reusable_caches(*, main_window=None) -> int:
    import shutil

    from core.auto_tracker import TRACKER_FILE
    from core.media_info import clear_media_probe_cache_memory
    from core.personalization.lora_vector_retriever import clear_lora_retrieval_caches
    from core.project.project_io import clear_project_file_cache
    from ui.style import clear_line_icon_cache

    removed_count = 0
    for cache_path in reusable_cache_paths():
        if not os.path.lexists(cache_path):
            continue
        if os.path.isdir(cache_path) and not os.path.islink(cache_path):
            shutil.rmtree(cache_path)
        else:
            os.remove(cache_path)
        removed_count += 1
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    if os.path.exists(TRACKER_FILE):
        os.remove(TRACKER_FILE)
        removed_count += 1
    clear_media_probe_cache_memory()
    clear_project_file_cache()
    clear_lora_retrieval_caches()
    clear_line_icon_cache()
    if main_window is not None and hasattr(main_window, "_cloud_sync_manager"):
        mgr = main_window._cloud_sync_manager
        mgr._size_cache.clear()
        mgr._in_flight.clear()
    runtime_cache_clear = getattr(main_window, "_clear_runtime_memory_caches", None) if main_window is not None else None
    if callable(runtime_cache_clear):
        runtime_cache_clear(include_gpu=False)
    return removed_count


def backup_project_file_copy(project_path: str) -> str:
    import datetime
    import shutil

    project_path = str(project_path or "")
    if not project_path or not os.path.exists(project_path):
        return ""
    backup_dir = os.path.join(os.path.dirname(project_path), "프로젝트백업")
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base, ext = os.path.splitext(os.path.basename(project_path))
    backup_path = os.path.join(backup_dir, f"{base}_{stamp}{ext or '.json'}")
    shutil.copy2(project_path, backup_path)
    return backup_path


def backup_subtitle_file_copy(subtitle_path: str) -> str:
    import datetime
    import shutil

    subtitle_path = str(subtitle_path or "")
    if not subtitle_path or not os.path.exists(subtitle_path):
        return ""
    backup_dir = os.path.join(os.path.dirname(subtitle_path), "자막백업")
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base, ext = os.path.splitext(os.path.basename(subtitle_path))
    backup_path = os.path.join(backup_dir, f"{base}_{stamp}{ext or '.srt'}")
    shutil.copy2(subtitle_path, backup_path)
    return backup_path


class EditorSaveManagerMixin:
    """저장/자동저장/dirty/백업/캐쉬 관리 전용 믹스인."""

    def _preferred_single_srt_output_path(self, media_path: str | None = None) -> str:
        source_srt_path = str(getattr(self, "_source_srt_path", "") or "").strip()
        if source_srt_path:
            return source_srt_path
        target_media_path = str(media_path or getattr(self, "media_path", "") or "").strip()
        if not target_media_path:
            return ""
        return get_srt_path(target_media_path)

    def _auto_save_interval_ms(self) -> int:
        return int(DEFAULT_EDITOR_AUTO_SAVE_INTERVAL_SEC * 1000)

    def _show_confirm_dialog(self, title, text):
        return confirm_save_changes(self, title=title)

    def _dirty_snapshot_blocks(self) -> list[tuple[str, dict[str, Any]]]:
        blocks: list[tuple[str, dict[str, Any]]] = []
        try:
            doc = self.text_edit.document()
        except Exception:
            return blocks
        for index in range(int(doc.blockCount() or 0)):
            block = doc.findBlockByNumber(index)
            data = block.userData()
            meta = {
                "spk_id": str(getattr(data, "spk_id", "00") or "00"),
                "start_sec": float(getattr(data, "start_sec", 0.0) or 0.0),
                "end_sec": getattr(data, "end_sec", None),
                "is_gap": bool(getattr(data, "is_gap", False)),
            }
            blocks.append((block.text(), meta))
        return blocks

    def _schedule_native_dirty_snapshot(self) -> None:
        generation = int(getattr(self, "_dirty_snapshot_generation", 0) or 0) + 1
        self._dirty_snapshot_generation = generation

        def worker() -> None:
            try:
                segments = [dict(seg) for seg in list(getattr(self, "_cached_segs", []) or [])]
                if not segments and hasattr(self, "_get_current_segments"):
                    segments = [dict(seg) for seg in list(self._get_current_segments() or [])]
                native_snapshot = capture_undo_snapshot_via_swift(
                    blocks=self._dirty_snapshot_blocks(),
                    segments=segments,
                    cursor_line=int(self.text_edit.textCursor().blockNumber()) if hasattr(self, "text_edit") else 0,
                    active_clip_idx=int(getattr(getattr(self, "timeline", None), "canvas", object()).__dict__.get("_active_clip_idx", 0) or 0),
                    project_boundary_times=list(getattr(self.window(), "_project_boundary_times", []) or []),
                )
                if int(getattr(self, "_dirty_snapshot_generation", 0) or 0) != generation:
                    return
                self._latest_dirty_native_snapshot = native_snapshot
            except Exception:
                pass

        threading.Thread(
            target=worker,
            daemon=True,
            name="editor-dirty-native-snapshot",
        ).start()

    def _mark_dirty(self):
        self._skip_prev_confirm_once = False
        started_editing = False
        if hasattr(self, "sm"):
            if hasattr(self.sm, "start_editing") and not getattr(self.sm, "is_locked", False):
                self.sm.start_editing()
                started_editing = True
            else:
                self.sm.is_dirty = True
        else:
            self._is_dirty = True
        self._is_dirty = True
        if started_editing and hasattr(self, "_note_editor_foreground_activity"):
            self._note_editor_foreground_activity()
        try:
            main_w = self.window()
            if hasattr(main_w, "_refresh_saved_status_label"):
                main_w._refresh_saved_status_label(is_dirty=True)
        except Exception:
            pass
        self._schedule_native_dirty_snapshot()

    def _deferred_editor_learning_hold_ms(self, *, trigger: str = "manual_save") -> int:
        try:
            main_w = self.window()
        except Exception:
            main_w = None
        default_hold = max(60_000, int(DEFAULT_DEFERRED_EDITOR_LEARNING_HOLD_MS))
        if main_w is None:
            return default_hold
        try:
            hold_ms = int(getattr(main_w, "_post_completion_idle_ms", default_hold) or default_hold)
        except Exception:
            hold_ms = default_hold
        return max(60_000, hold_ms)

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
                    "speaker_list": [str(item or "") for item in list(seg.get("speaker_list") or [])],
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

    def _current_project_path_for_dirty_check(self) -> str:
        for owner in (self, self.window() if hasattr(self, "window") else None):
            try:
                project_path = str(getattr(owner, "_current_project_path", "") or "")
            except Exception:
                project_path = ""
            if project_path:
                return project_path
        return ""

    def _project_file_dirty_signature(self, project_path: str | None = None) -> str:
        project_path = str(project_path or self._current_project_path_for_dirty_check() or "")
        if not project_path or not os.path.exists(project_path):
            return ""
        with open(project_path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()

    def _remember_saved_project_file(self, project_path: str | None = None):
        project_path = str(project_path or self._current_project_path_for_dirty_check() or "")
        self._saved_project_path = project_path
        try:
            self._saved_project_signature = self._project_file_dirty_signature(project_path)
        except Exception:
            self._saved_project_signature = ""

    def _project_file_has_unsaved_changes(self) -> bool:
        saved_path = str(getattr(self, "_saved_project_path", "") or "")
        saved_sig = str(getattr(self, "_saved_project_signature", "") or "")
        project_path = self._current_project_path_for_dirty_check()
        if not saved_path or not saved_sig or not project_path:
            return False
        if os.path.abspath(project_path) != os.path.abspath(saved_path):
            return True
        pending_path = str(getattr(self, "_project_analysis_refresh_pending_path", "") or "")
        if bool(getattr(self, "_project_analysis_refresh_pending", False)) and (
            not pending_path or os.path.abspath(project_path) == os.path.abspath(pending_path)
        ):
            return False
        try:
            current_sig = self._project_file_dirty_signature(project_path)
        except Exception:
            return False
        return bool(current_sig and current_sig != saved_sig)

    def _mark_unsaved_project_change_detected(self):
        self._mark_dirty()

    def _has_unsaved_changes(self) -> bool:
        saved_sig = getattr(self, "_saved_segments_signature", None)
        if saved_sig:
            try:
                if self._segments_dirty_signature() != saved_sig:
                    return True
            except Exception:
                pass
        try:
            if bool(getattr(self.sm, "is_dirty", False)):
                return True
        except Exception:
            if bool(getattr(self, "_is_dirty", False)):
                return True
        try:
            if self._project_file_has_unsaved_changes():
                self._mark_unsaved_project_change_detected()
                return True
        except Exception:
            pass
        return bool(getattr(self, "_is_dirty", False))

    def _mark_save_completed(self, touch_saved_time: bool = True) -> bool:
        self._is_dirty = False
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

    def _queue_row_for_current_media(self):
        try:
            main_w = self.window()
        except Exception:
            return None
        return find_queue_row_for_media(
            main_w,
            media_path=getattr(self, "media_path", ""),
        )

    def _sync_queue_saved_state(self):
        try:
            main_w = self.window()
        except Exception:
            return
        try:
            sync_saved_queue_state(
                main_w,
                media_path=getattr(self, "media_path", ""),
            )
        except Exception:
            pass

    def _flush_pending_segment_queue_now(self):
        try:
            timer = getattr(self, "_queue_timer", None)
            if timer is not None and hasattr(timer, "isActive") and timer.isActive():
                timer.stop()
        except Exception:
            pass
        flush = getattr(self, "_flush_queue", None)
        if not callable(flush):
            return
        max_passes = 512
        for _ in range(max_passes):
            try:
                queue = list(getattr(self, "_segment_queue", []) or [])
            except Exception:
                queue = []
            if not queue:
                break
            before_count = len(queue)
            try:
                flush()
            except Exception:
                break
            try:
                remaining = list(getattr(self, "_segment_queue", []) or [])
            except Exception:
                remaining = []
            if not remaining:
                break
            if len(remaining) >= before_count:
                try:
                    get_logger().log("⚠️ 생성 완료 queue flush가 더 진행되지 않아 남은 자막 배치를 보류합니다.")
                except Exception:
                    pass
                break
        try:
            timer = getattr(self, "_queue_timer", None)
            if timer is not None and hasattr(timer, "isActive") and timer.isActive():
                timer.stop()
        except Exception:
            pass

    def _project_provisional_cut_boundaries_for_save(self) -> list[dict]:
        provisional_cut_boundaries = []
        try:
            if hasattr(self, "timeline") and hasattr(self.timeline, "canvas"):
                canvas = self.timeline.canvas
                provisional_cut_boundaries = list(getattr(canvas, "scan_boundary_times", []) or [])
        except Exception:
            provisional_cut_boundaries = []
        if not provisional_cut_boundaries:
            provisional_cut_boundaries = list(getattr(self, "_auto_cut_boundary_scan_lines", []) or [])

        scan_active = bool(getattr(self, "_auto_cut_boundary_scan_active", False))
        if scan_active:
            return list(provisional_cut_boundaries or [])

        try:
            main_w = self.window()
        except Exception:
            return list(provisional_cut_boundaries or [])

        backend_candidates = [
            getattr(main_w, "backend", None),
            getattr(main_w, "backend_fast", None),
        ]
        for backend in backend_candidates:
            if backend is None:
                continue
            try:
                prescan = getattr(backend, "_cut_boundary_prescan_thread", None)
                follower = getattr(backend, "_cut_boundary_follower_thread", None)
                scan_busy = bool(
                    (prescan is not None and prescan.is_alive())
                    or (follower is not None and follower.is_alive())
                )
                scan_completed = bool(getattr(backend, "_cut_boundary_prescan_completed", False))
            except Exception:
                continue
            if scan_completed and not scan_busy:
                return []
        return list(provisional_cut_boundaries or [])

    def _segments_for_srt_output(self, segs: list[dict]) -> list[dict]:
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

    def _persist_editor_srts(
        self,
        segs: list[dict],
        *,
        autosave: bool = False,
        write_backup: bool = True,
    ) -> bool:
        main_w = self.window()
        multiclip_files = list(getattr(main_w, "_multiclip_files", []) or [])
        srt_output_segs = self._segments_for_srt_output(segs)
        saved_any = False
        if len(multiclip_files) > 1:
            saved_any = self._save_multiclip_srts(srt_output_segs, multiclip_files, write_backup=write_backup)
        elif getattr(self, "media_path", None):
            srt_path = self._preferred_single_srt_output_path(self.media_path)
            if not srt_path:
                get_logger().log("⚠️ 저장 실패: SRT 저장 경로를 만들 수 없습니다.")
                return False
            save_srt(
                srt_output_segs,
                srt_path,
                fps=getattr(self, "video_fps", 30.0),
                write_backup=write_backup,
            )
            verb = "자동 저장 완료" if autosave else "저장 완료"
            get_logger().log(f"💾 {verb}: {os.path.basename(srt_path)}")
            self._last_saved_srt_outputs = [(srt_path, self.media_path)]
            saved_any = True
        else:
            get_logger().log("⚠️ 저장 실패: media_path가 없어 SRT 저장 경로를 만들 수 없습니다.")
            return False
        if not saved_any:
            get_logger().log("⚠️ 저장 실패: 실제로 저장된 자막 파일이 없습니다.")
            return False
        return True

    def _schedule_project_analysis_artifacts_refresh(
        self,
        project_path: str,
        segs: list[dict],
        settings: dict | None = None,
        *,
        saved_segments_signature: str = "",
    ) -> None:
        project_path = str(project_path or "")
        if not project_path or not os.path.exists(project_path):
            return
        segments = [dict(seg) for seg in list(segs or []) if isinstance(seg, dict)]
        if not segments:
            return
        settings_snapshot = dict(settings or getattr(self, "settings", {}) or {})
        generation = int(getattr(self, "_project_analysis_refresh_generation", 0) or 0) + 1
        self._project_analysis_refresh_generation = generation
        self._project_analysis_refresh_pending = True
        self._project_analysis_refresh_pending_path = project_path
        self._project_analysis_refresh_pending_generation = generation

        def worker() -> None:
            graph_result = None
            lattice_result = None
            try:
                from core.audio.stt_lattice import persist_stt_lattice_artifact
                from core.engine.subtitle_accuracy_graph import persist_subtitle_accuracy_graph
                from core.project.project_io import read_project_file, write_project_file

                try:
                    project = read_project_file(project_path)
                except Exception:
                    project = {}
                media_items = list(project.get("media") or [])
                primary_media_path = ""
                if media_items and isinstance(media_items[0], dict):
                    primary_media_path = str(media_items[0].get("path") or "")
                if settings_snapshot.get("accuracy_graph_persist_enabled", True):
                    graph_result = persist_subtitle_accuracy_graph(
                        segments,
                        settings_snapshot,
                        media_path=primary_media_path,
                        project_path=project_path,
                    )
                if settings_snapshot.get("stt_lattice_persist_enabled", True):
                    lattice_result = persist_stt_lattice_artifact(
                        segments,
                        settings_snapshot,
                        media_path=primary_media_path,
                        project_path=project_path,
                    )
                if int(getattr(self, "_project_analysis_refresh_generation", 0) or 0) != generation:
                    return
                latest = read_project_file(project_path)
                latest.setdefault("analysis", {})
                editor_analysis = ((latest.setdefault("editor_state", {}) or {}).setdefault("analysis", {}))
                if graph_result is not None:
                    latest["analysis"]["subtitle_accuracy_graph_schema"] = graph_result.get("schema")
                    latest["analysis"]["subtitle_accuracy_graph_path"] = graph_result.get("path", "")
                    latest["analysis"]["subtitle_accuracy_graph_summary"] = graph_result.get("summary", {})
                    latest["analysis"]["subtitle_accuracy_graph_segment_count"] = graph_result.get("segment_count", 0)
                    editor_analysis["subtitle_accuracy_graph_path"] = graph_result.get("path", "")
                    editor_analysis["subtitle_accuracy_graph_summary"] = graph_result.get("summary", {})
                if lattice_result is not None:
                    latest["analysis"]["stt_lattice_schema"] = lattice_result.get("schema")
                    latest["analysis"]["stt_lattice_artifact_path"] = lattice_result.get("path", "")
                    latest["analysis"]["stt_lattice_summary"] = lattice_result.get("summary", {})
                    latest["analysis"]["stt_lattice_segment_count"] = lattice_result.get("segment_count", 0)
                    editor_analysis["stt_lattice_artifact_path"] = lattice_result.get("path", "")
                    editor_analysis["stt_lattice_summary"] = lattice_result.get("summary", {})
                write_project_file(project_path, latest)
                if saved_segments_signature and saved_segments_signature == str(getattr(self, "_saved_segments_signature", "") or ""):
                    self._saved_project_path = project_path
                    self._saved_project_signature = self._project_file_dirty_signature(project_path)
            except Exception as exc:
                get_logger().log(f"⚠️ 프로젝트 분석 아티팩트 비동기 저장 실패: {exc}")
            finally:
                if int(getattr(self, "_project_analysis_refresh_pending_generation", 0) or 0) == generation:
                    self._project_analysis_refresh_pending = False
                    self._project_analysis_refresh_pending_path = ""

        def launch_worker() -> None:
            if int(getattr(self, "_project_analysis_refresh_generation", 0) or 0) != generation:
                return
            threading.Thread(
                target=worker,
                name="editor-project-analysis-artifacts",
                daemon=True,
            ).start()

        QTimer.singleShot(DEFAULT_PROJECT_ANALYSIS_REFRESH_DELAY_MS, launch_worker)

    def _on_save(
        self,
        *args,
        skip_auto_next=False,
        write_backup: bool = True,
        schedule_analysis_refresh: bool = True,
        queue_learning: bool = True,
        allow_project_create: bool = True,
        auto_export: bool | None = None,
        force: bool = False,
        cancel_post_generation_roughcut: bool = True,
    ):
        cancel_roughcut = getattr(self, "_cancel_post_generation_roughcut_draft", None)
        if bool(cancel_post_generation_roughcut) and callable(cancel_roughcut):
            try:
                cancel_roughcut(reason="수동 저장")
            except Exception as exc:
                get_logger().log(f"⚠️ 수동 저장 러프컷 취소 실패: {type(exc).__name__}: {exc}")
        has_saved_reference = bool(
            str(getattr(self, "_saved_segments_signature", "") or "").strip()
            or str(self._current_project_path_for_dirty_check() or "").strip()
        )
        if has_saved_reference and not bool(force):
            try:
                if not self._has_unsaved_changes():
                    self._mark_save_completed(touch_saved_time=False)
                    self._autosave_requires_manual_save = False
                    get_logger().log("💾 저장 생략: 변경사항이 없습니다.")
                    return True
            except Exception:
                pass
        self._flush_pending_segment_queue_now()
        segs = self._get_current_segments()
        if not segs and (
            bool(getattr(self, "_subtitle_generation_completed", False))
            or bool(getattr(self, "_process_completed_finalized", False))
        ):
            recover = getattr(self, "_recover_generation_segments_from_backend_backup", None)
            if callable(recover):
                try:
                    if recover():
                        segs = self._get_current_segments()
                except Exception:
                    pass
        if not segs:
            get_logger().log("💾 저장 취소: 저장할 자막 세그먼트가 없습니다.")
            return False
        if hasattr(self, "_warn_pending_stt_before_save") and not self._warn_pending_stt_before_save(segs):
            get_logger().log("💾 저장 취소: STT 미완료 세그먼트 확인 필요")
            return False

        self._last_saved_srt_outputs = []
        try:
            main_w = self.window()
            if not self._persist_editor_srts(segs, autosave=False, write_backup=write_backup):
                return False
        except Exception as exc:
            get_logger().log(f"⚠️ 저장 실패: {exc}")
            return False

        if not skip_auto_next:
            self._skip_prev_confirm_once = True

        self._remember_saved_segments(segs)
        try:
            project_path = self._auto_save_project(
                segs,
                persist_analysis_artifacts=False,
                allow_create=allow_project_create,
            )
        except Exception as exc:
            get_logger().log(f"⚠️ 프로젝트 자동 저장 실패: {exc}")
            project_path = ""
        try:
            should_auto_export = self._should_auto_export_after_editor_save() if auto_export is None else bool(auto_export)
            if should_auto_export:
                self._schedule_auto_export_saved_subtitle_videos()
        except Exception as exc:
            get_logger().log(f"⚠️ 자막영상 자동 출력 실패: {exc}")
        self._remember_saved_project_file(project_path)
        if schedule_analysis_refresh:
            try:
                self._schedule_project_analysis_artifacts_refresh(
                    project_path,
                    segs,
                    dict(getattr(self, "settings", {}) or {}),
                    saved_segments_signature=str(getattr(self, "_saved_segments_signature", "") or ""),
                )
            except Exception as exc:
                get_logger().log(f"⚠️ 프로젝트 분석 아티팩트 예약 실패: {exc}")
        self._mark_save_completed(touch_saved_time=True)
        self._autosave_requires_manual_save = False
        self._sync_queue_saved_state()
        if queue_learning:
            try:
                from core.personalization.deferred_editor_learning import enqueue_deferred_editor_learning

                hold_ms = self._deferred_editor_learning_hold_ms(trigger="manual_save")
                pause_lora = getattr(main_w, "_pause_personalization_for_foreground_activity", None)
                if callable(pause_lora):
                    try:
                        pause_lora("manual_save", hold_ms=hold_ms)
                    except Exception:
                        pause_lora("manual_save")
                settings = dict(getattr(self, "settings", {}) or {})
                saved_outputs = list(getattr(self, "_last_saved_srt_outputs", []) or [])
                first_subtitle_path = str(saved_outputs[0][0]) if saved_outputs else ""
                queued = enqueue_deferred_editor_learning(
                    [dict(seg) for seg in list(segs or []) if not seg.get("is_gap")],
                    media_path=str(getattr(self, "media_path", "") or ""),
                    subtitle_path=first_subtitle_path,
                    project_path=str(getattr(main_w, "_current_project_path", "") or ""),
                    trigger="manual_save",
                    settings=settings,
                    defer_for_ms=hold_ms,
                )
                if queued.get("queued"):
                    get_logger().log("🧠 [LoRA] 저장 자막 학습은 Home-idle 큐로 넘겼습니다.")
            except Exception as exc:
                get_logger().log(f"⚠️ 개인화 학습 큐 등록 실패(저장): {exc}")
        return True

    def _on_save_for_exit(self) -> bool:
        return bool(
            self._on_save(
                skip_auto_next=True,
                write_backup=False,
                schedule_analysis_refresh=False,
                queue_learning=True,
                allow_project_create=False,
                auto_export=False,
            )
        )

    def _save_multiclip_srts(self, segs, multiclip_files, *, write_backup: bool = True):
        main_w = self.window()
        boundaries = (
            getattr(self, "_multiclip_boundaries", None)
            or getattr(main_w, "_multiclip_boundaries", None)
            or (getattr(self.timeline.canvas, "_multiclip_boxes", None) if hasattr(self, "timeline") else None)
            or []
        )
        reuse_indices = (
            getattr(self, "_reuse_clip_indices", None)
            or getattr(main_w, "_reuse_clip_indices", None)
            or set()
        )
        if not boundaries:
            get_logger().log("⚠️ 멀티클립 boundaries 없음 — 단일 파일 저장으로 대체")
            if getattr(self, "media_path", None):
                srt_path = get_srt_path(self.media_path)
                non_gap = [s for s in segs if not s.get("is_gap") and s.get("text", "").strip()]
                save_srt(non_gap, srt_path, fps=getattr(self, "video_fps", 30.0), write_backup=write_backup)
                get_logger().log(f"💾 저장 완료: {os.path.basename(srt_path)}")
                return True
            return False

        def _clip_idx_for(start_sec):
            for i, bd in enumerate(boundaries):
                if bd["start"] <= start_sec < bd["end"]:
                    return i
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

        clip_segs = {}
        for seg in segs:
            if seg.get("is_gap") or not seg.get("text", "").strip():
                continue
            cidx = _seg_clip_idx(seg)
            clip_segs.setdefault(cidx, []).append(seg)

        saved_count = 0
        saved_outputs = []
        for i, clip_file in enumerate(multiclip_files):
            if i in reuse_indices:
                continue
            srt_path = get_srt_path(clip_file)
            c_segs = clip_segs.get(i, [])
            if not c_segs:
                continue
            offset = boundaries[i].get("start", 0.0) if i < len(boundaries) else 0.0
            local_segs = []
            for seg in c_segs:
                ls = dict(seg)
                ls["start"] = max(0.0, float(ls["start"]) - offset)
                ls["end"] = max(0.0, float(ls["end"]) - offset)
                local_segs.append(ls)
            save_srt(local_segs, srt_path, fps=getattr(self, "video_fps", 30.0), write_backup=write_backup)
            saved_outputs.append((srt_path, clip_file))
            saved_count += 1
            get_logger().log(f"💾 개별 저장: {os.path.basename(srt_path)} ({len(local_segs)}개)")

        project_path = getattr(main_w, "_current_project_path", None)
        proj_name = os.path.splitext(os.path.basename(project_path))[0] if project_path else os.path.splitext(os.path.basename(multiclip_files[0]))[0]
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
            save_srt(combined_segs, combined_srt_path, fps=getattr(self, "video_fps", 30.0), write_backup=write_backup)
            saved_outputs.append((combined_srt_path, combined_srt_path))
            combined_saved = True
            get_logger().log(f"💾 통합 저장: {os.path.basename(combined_srt_path)} ({len(combined_segs)}개, 기존자막 {len(reuse_indices)}클립 제외)")
        elif segs:
            non_gap = [s for s in segs if not s.get("is_gap") and s.get("text", "").strip()]
            save_srt(non_gap, combined_srt_path, fps=getattr(self, "video_fps", 30.0), write_backup=write_backup)
            saved_outputs.append((combined_srt_path, combined_srt_path))
            combined_saved = True
            get_logger().log(f"💾 통합 저장: {os.path.basename(combined_srt_path)} ({len(non_gap)}개, 전체 포함)")

        get_logger().log(f"✅ 멀티클립 저장 완료: 개별 {saved_count}개 + 통합 1개")
        self._last_saved_srt_outputs = saved_outputs
        return bool(saved_count or combined_saved)

    def _should_auto_export_after_editor_save(self) -> bool:
        try:
            main_w = self.window()
        except Exception:
            return False
        return bool(getattr(main_w, "_is_auto_pipeline", False) or getattr(main_w, "_auto_processing_active", False))

    def _schedule_auto_export_saved_subtitle_videos(self, *, delay_ms: int = 1500):
        outputs = list(getattr(self, "_last_saved_srt_outputs", []) or [])
        if not outputs:
            return
        generation = int(getattr(self, "_auto_export_video_generation", 0) or 0) + 1
        self._auto_export_video_generation = generation
        self._auto_export_video_outputs = outputs
        QTimer.singleShot(max(0, int(delay_ms)), lambda gen=generation: self._run_scheduled_auto_export(gen))

    def _run_scheduled_auto_export(self, generation: int):
        if int(generation or 0) != int(getattr(self, "_auto_export_video_generation", 0) or 0):
            return
        if bool(getattr(self, "_auto_export_video_running", False)):
            return
        try:
            main_w = self.window()
            if hasattr(main_w, "_is_editor_actively_editing") and main_w._is_editor_actively_editing():
                self._schedule_auto_export_saved_subtitle_videos(delay_ms=10_000)
                return
        except Exception:
            pass
        outputs = list(getattr(self, "_auto_export_video_outputs", []) or [])
        if not outputs:
            return
        self._auto_export_video_running = True

        def _worker():
            try:
                self._auto_export_saved_subtitle_videos(outputs=outputs)
            finally:
                self._auto_export_video_running = False

        threading.Thread(target=_worker, daemon=True, name="editor-subtitle-video-export").start()

    def _auto_export_saved_subtitle_videos(self, *, outputs: list | None = None):
        outputs = list(outputs if outputs is not None else getattr(self, "_last_saved_srt_outputs", []) or [])
        if not outputs:
            return
        try:
            from ui.dialogs.export_dialog import _load_es
            from core.renderer import render_subtitle_mov

            export_settings = _load_es()
        except Exception as exc:
            get_logger().log(f"⚠️ 자막영상 출력 설정 로드 실패: {exc}")
            return
        total = len(outputs)
        for idx, item in enumerate(outputs, start=1):
            try:
                srt_path, target_file = item
                if not srt_path or not os.path.exists(srt_path):
                    continue
                label = os.path.basename(str(target_file or srt_path))
                get_logger().log(f"🎥 자막영상 자동 출력 [{idx}/{total}]: {label}")
                render_subtitle_mov(srt_path, target_file or srt_path, export_settings, idx, total)
            except Exception as exc:
                get_logger().log(f"⚠️ 자막영상 자동 출력 실패 [{idx}/{total}]: {exc}")

    def _auto_save_project(
        self,
        segs: list = None,
        *,
        persist_analysis_artifacts: bool = False,
        rewrite_stt_reference_tracks: bool = False,
        allow_create: bool = True,
    ) -> str:
        from core.project.project_manager import save_project, create_project

        media_path = getattr(self, "media_path", None)
        if not media_path:
            return ""
        if segs is None:
            try:
                segs = self._get_current_segments()
            except Exception:
                segs = []
        main_w = self.window()
        project_path = getattr(main_w, "_current_project_path", None)
        if not project_path:
            if not allow_create:
                return ""
            base_name = os.path.splitext(os.path.basename(media_path))[0]
            project_path = create_project(
                name=base_name,
                media_paths=[media_path],
                srt_path=get_srt_path(media_path),
                user_settings=dict(getattr(self, "settings", {}) or {}),
                # 수동 저장의 자동 프로젝트 생성은 저장만 해야 하며 러프컷 LLM prefill을 시작하면 안 된다.
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
            get_logger().log(f"📝 프로젝트 자동 생성: {os.path.basename(project_path)}")

        workspace = {}
        if hasattr(self, "video_player"):
            workspace["last_playhead"] = getattr(self.video_player, "current_time", 0.0)
        if hasattr(self, "text_edit"):
            workspace["last_cursor_block"] = self.text_edit.textCursor().blockNumber()
        if hasattr(self, "splitter"):
            workspace["splitter_sizes"] = self.splitter.sizes()
        try:
            workspace["terminal_visible"] = main_w._log_visible
        except Exception:
            pass
        workspace["dashboard_mode"] = getattr(main_w, "_dashboard_mode", "dashboard") or "dashboard"
        workspace["project_panel_visible"] = bool(getattr(main_w, "_project_panel_visible", True))
        media_paths = list(getattr(main_w, "_multiclip_files", []) or []) or [media_path]
        workspace["selected_segment_line"] = workspace.get("last_cursor_block", 0)
        try:
            workspace["edit_lock"] = bool(self.timeline.lock_chk.isChecked())
        except Exception:
            workspace["edit_lock"] = False
        workspace["active_clip_idx"] = int(getattr(self.timeline.canvas, "_active_clip_idx", getattr(main_w, "_active_clip_idx", 0)) or 0)
        workspace["active_work_mode"] = normalize_work_mode(getattr(main_w, "_current_work_mode", EDITOR_MODE))
        aux_state = collect_editor_project_aux_state(self)
        stt_preview_segments = aux_state["stt_preview_segments"]
        voice_activity_segments = aux_state["voice_activity_segments"]
        provisional_cut_boundaries = aux_state["provisional_cut_boundaries"]
        middle_segments = aux_state["middle_segments"]
        preliminary_middle_segments = aux_state["preliminary_middle_segments"]
        roughcut_result = aux_state["roughcut_result"]
        stt_mode_state = None
        stt_mode_learning = None
        if getattr(self, "_stt_mode_enabled", False) or getattr(self, "_stt_work_segments", None):
            try:
                from core.stt_mode.lora_runtime import export_stt_runtime_bundle
                from core.stt_mode.project_state import build_stt_mode_state, default_stt_mode_learning

                stt_bundle = export_stt_runtime_bundle(
                    project_path=project_path,
                    media_path=media_path,
                    settings=dict(getattr(self, "settings", {}) or {}),
                    work_segments=list(getattr(self, "_stt_work_segments", []) or []),
                    raw_segments=list(getattr(self, "_stt_raw_dictation_segments", []) or []),
                    final_segments=list(getattr(self, "_stt_final_segments", []) or []),
                    learning_events=list(getattr(self, "_stt_learning_events", []) or []),
                )
                if stt_bundle:
                    self._stt_lora_bundle_info = dict(stt_bundle)
                    self._stt_adapter_refs = dict(stt_bundle.get("adapter_refs", {}) or {})
                stt_mode_state = build_stt_mode_state(
                    media_path=media_path,
                    work_segments=list(getattr(self, "_stt_work_segments", []) or []),
                    raw_dictation_segments=list(getattr(self, "_stt_raw_dictation_segments", []) or []),
                    rolling_windows=list(getattr(self, "_stt_rolling_windows", []) or []),
                    final_segments=list(getattr(self, "_stt_final_segments", []) or []),
                    active_work_segment_id=str(getattr(self, "_stt_state_detail", {}).get("segment_id", "") or ""),
                    primary_fps=getattr(getattr(self, "timeline", None), "fps", 30.0),
                    adapter_refs=dict(getattr(self, "_stt_adapter_refs", {}) or {}),
                )
                stt_mode_learning = default_stt_mode_learning(
                    {"events": list(getattr(self, "_stt_learning_events", []) or []), "learning_opt_in": True}
                )
            except Exception as exc:
                get_logger().log(f"⚠️ STT 프로젝트 상태 구성 실패: {exc}")
        save_project(
            filepath=project_path,
            media_paths=media_paths,
            srt_path=get_srt_path(media_path),
            segments=segs,
            middle_segments=middle_segments,
            roughcut_result=roughcut_result,
            user_settings=dict(getattr(self, "settings", {}) or {}),
            workspace=workspace,
            active_work_mode=workspace["active_work_mode"],
            voice_activity_segments=voice_activity_segments,
            stt_preview_segments=stt_preview_segments,
            stt_mode_state=stt_mode_state,
            stt_mode_learning=stt_mode_learning,
            provisional_cut_boundaries=provisional_cut_boundaries,
            persist_analysis_artifacts=bool(persist_analysis_artifacts),
            rewrite_stt_reference_tracks=bool(rewrite_stt_reference_tracks),
            preliminary_middle_segments=preliminary_middle_segments,
        )
        get_logger().log(f"📦 프로젝트 저장 완료: {os.path.basename(project_path)}")
        return project_path

    def _editor_auto_save_allowed(self) -> bool:
        return False

    def _on_auto_save(self):
        return

    def _confirm_close_before_exit(self, title: str = "종료 확인") -> bool:
        is_dirty = False
        try:
            is_dirty = self._has_unsaved_changes()
        except Exception:
            is_dirty = bool(getattr(self, "_is_dirty", False))
        if not is_dirty:
            return True
        reply = self._show_confirm_dialog(title, "저장되지 않은 변경사항이 있습니다.\n저장하시겠습니까?")
        if reply == QMessageBox.StandardButton.Cancel:
            return False
        if reply == QMessageBox.StandardButton.Yes:
            return bool(self._on_save_for_exit())
        return True


__all__ = [
    "EditorSaveManagerMixin",
    "backup_subtitle_file_copy",
    "backup_project_file_copy",
    "clear_reusable_caches",
    "reusable_cache_paths",
]
