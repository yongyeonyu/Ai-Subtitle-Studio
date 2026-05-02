# Version: 02.03.02
# Phase: PHASE1-B
"""
core/pipeline/pipeline_helpers.py
PipelineHelpersMixin — 백업 · 재시작 · 저장/내보내기 · 렌더링 · 화자분리 · ntfy · 프리페치 · 오디오 추출
"""
import os
import json
import threading
import traceback
import time

import config
from logger import get_logger
from core.audio.media_processor import VideoProcessor
from core.settings import load_settings, get_model_key


class PipelineHelpersMixin:
    """CoreBackend 에서 사용하는 공통 헬퍼 메서드 모음."""

    def _align_subtitle_segments_to_vad(self, segments, vad_segments, *, context: str = "자막") -> list[dict]:
        """VAD 음성 경계로 자막 시작/끝을 보정한 뒤 에디터로 넘깁니다."""
        out = [dict(seg) for seg in (segments or [])]
        if not out or not vad_segments:
            return out
        try:
            settings = load_settings()
        except Exception:
            settings = {}
        if not bool(settings.get("vad_post_stt_align_enabled", True)):
            return out

        try:
            from core.subtitle_quality.vad_alignment_checker import adjust_segments_to_vad_boundaries

            adjusted, adjusted_count = adjust_segments_to_vad_boundaries(
                out,
                vad_segments,
                max_shift_sec=float(settings.get("vad_post_stt_max_shift_sec", 0.7) or 0.7),
                edge_pad_sec=float(settings.get("vad_post_stt_edge_pad_sec", 0.04) or 0.04),
            )
            if adjusted_count:
                get_logger().log(f"  🎯 [VAD 후처리] {context} 자막 위치 {adjusted_count}개 보정 후 자막 메뉴로 전달")
            return adjusted
        except Exception as exc:
            get_logger().log(f"  ⚠️ [VAD 후처리] {context} 자막 위치 보정 실패: {exc}")
            return out

    def _project_cut_boundaries_for_pipeline(self) -> list[dict]:
        """Return saved visual cut boundaries from the current project file."""
        try:
            from core.cut_boundary import project_cut_boundaries

            ui = getattr(self, "ui", None)
            project_path = str(getattr(ui, "_current_project_path", "") or "")
            if not project_path or not os.path.exists(project_path):
                return []
            import json

            with open(project_path, "r", encoding="utf-8") as f:
                return project_cut_boundaries(json.load(f))
        except Exception:
            return []

    def _cut_boundary_cache_path_for_start(self, files: list[str], settings: dict) -> str:
        """Return reusable cut-boundary cache path for the current media/settings."""
        import hashlib
        try:
            import config
            cache_root = os.path.join(config.OUTPUT_DIR, "cut_boundary_cache")
        except Exception:
            cache_root = os.path.join("output", "cut_boundary_cache")

        os.makedirs(cache_root, exist_ok=True)

        payload = {
            "version": 2,
            "files": [],
            "settings": {
                "scan_cut_auto_sample_step_sec": settings.get("scan_cut_auto_sample_step_sec", 1.0),
                "scan_cut_auto_threshold": settings.get("scan_cut_auto_threshold", settings.get("scan_cut_threshold", 24.0)),
                "scan_cut_threshold": settings.get("scan_cut_threshold", 24.0),
                "scan_cut_mode": settings.get("scan_cut_mode", ""),
            },
        }

        for p in list(files or []):
            try:
                st = os.stat(p)
                payload["files"].append({
                    "path": os.path.abspath(p),
                    "size": int(st.st_size),
                    "mtime_ns": int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))),
                })
            except Exception:
                payload["files"].append({
                    "path": os.path.abspath(str(p)),
                    "size": 0,
                    "mtime_ns": 0,
                })

        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        key = hashlib.sha256(raw).hexdigest()[:24]
        return os.path.join(cache_root, f"cut_boundaries_{key}.json")

    def _load_cut_boundary_cache_for_start(self, project_path: str, files: list[str], settings: dict) -> list[dict]:
        """Load cached cut boundaries and hydrate only project.analysis.cut_boundaries.

        IMPORTANT:
        - Never replace/move/copy the project file itself.
        - Only inject cached analysis.cut_boundaries into the current project.
        """
        try:
            from core.cut_boundary import normalize_cut_boundaries, sync_project_cut_boundaries

            cache_path = self._cut_boundary_cache_path_for_start(files, settings)
            if not os.path.exists(cache_path):
                return []

            with open(cache_path, "r", encoding="utf-8") as f:
                payload = json.load(f)

            analysis = payload.get("analysis", {}) if isinstance(payload, dict) else {}
            rows = analysis.get("cut_boundaries", [])

            # Backward compatibility with older cache format
            if not rows:
                rows = payload.get("cut_boundaries", []) if isinstance(payload, dict) else []

            rows = normalize_cut_boundaries(rows or [])
            if not rows:
                return []

            # ✅ 핵심: 현재 프로젝트 파일은 그대로 두고 analysis.cut_boundaries만 주입
            if project_path and os.path.exists(project_path):
                with open(project_path, "r", encoding="utf-8") as f:
                    project = json.load(f)

                project.setdefault("analysis", {})
                project["analysis"]["cut_boundaries"] = list(rows)
                project["analysis"]["cut_boundary_prescan_done"] = True
                project["analysis"]["cut_boundary_cache_path"] = cache_path
                project["analysis"]["cut_boundary_cache_type"] = "cut_boundaries_only"

                sync_project_cut_boundaries(project, settings=settings)

                with open(project_path, "w", encoding="utf-8") as f:
                    json.dump(project, f, ensure_ascii=False, indent=2)

            get_logger().log(
                f"  ♻️ [컷 경계] 캐시 재사용: {len(rows)}개 "
                f"(analysis.cut_boundaries only, {cache_path})"
            )
            self._ui_emit("_sig_refresh_cut_boundary_placeholder")
            return rows
        except Exception as exc:
            get_logger().log(f"  ⚠️ [컷 경계] 캐시 불러오기 실패: {exc}")
            return []

    def _save_cut_boundary_cache_for_start(self, files: list[str], settings: dict, rows: list[dict]) -> None:
        """Save only cut-boundary analysis data for future reuse.

        IMPORTANT:
        - Do NOT move/copy the actual project file into cache.
        - The project file remains the source of truth for the current work.
        - Cache stores only analysis.cut_boundaries-compatible rows.
        """
        try:
            import time
            cache_path = self._cut_boundary_cache_path_for_start(files, settings)

            payload = {
                "version": 2,
                "created_at": time.time(),
                "cache_type": "cut_boundaries_only",
                "files": [],
                "settings": {
                    "scan_cut_auto_sample_step_sec": settings.get("scan_cut_auto_sample_step_sec", 1.0),
                    "scan_cut_auto_threshold": settings.get("scan_cut_auto_threshold", settings.get("scan_cut_threshold", 24.0)),
                    "scan_cut_threshold": settings.get("scan_cut_threshold", 24.0),
                    "scan_cut_mode": settings.get("scan_cut_mode", ""),
                },
                # ✅ 핵심: 프로젝트 전체가 아니라 컷 경계 데이터만 저장
                "analysis": {
                    "cut_boundaries": list(rows or []),
                },
            }

            for p in list(files or []):
                try:
                    st = os.stat(p)
                    payload["files"].append({
                        "path": os.path.abspath(str(p)),
                        "size": int(st.st_size),
                        "mtime_ns": int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))),
                    })
                except Exception:
                    payload["files"].append({
                        "path": os.path.abspath(str(p)),
                        "size": 0,
                        "mtime_ns": 0,
                    })

            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

            get_logger().log(
                f"  💾 [컷 경계] 캐시 저장 완료: {len(rows or [])}개 "
                f"(analysis.cut_boundaries only, {cache_path})"
            )
        except Exception as exc:
            get_logger().log(f"  ⚠️ [컷 경계] 캐시 저장 실패: {exc}")

    def _wait_cut_boundary_prescan_before_stt(self):
        """Block backend pipeline thread until cut-boundary prescan is done.

        This does not block the Qt UI thread. It only prevents STT1/STT2 from
        starting before the absolute cut-boundary middle segments are ready.
        """
        try:
            thread = getattr(self, "_cut_boundary_prescan_thread", None)
            if thread is not None and thread.is_alive():
                get_logger().log("  🎬 [컷 경계] STT 시작 전 자동 분석 완료 대기 중...")
                thread.join()
                get_logger().log("  ✅ [컷 경계] STT 시작 전 자동 분석 완료")
                try:
                    self._ui_emit("_sig_refresh_cut_boundary_placeholder")
                except Exception:
                    pass
        except Exception as exc:
            get_logger().log(f"  ⚠️ [컷 경계] STT 시작 전 대기 실패: {exc}")


    def _auto_scan_cut_boundaries_for_start(self, project_path: str, files: list[str]) -> list[dict]:
        """Start cut-boundary prescan without blocking the Qt/UI thread.

        The old implementation ran detect_media_cut_boundaries() synchronously.
        That made the app show a busy cursor and prevented other buttons from
        being selected while the scan was running.
        """
        try:
            import threading

            old_thread = getattr(self, "_cut_boundary_prescan_thread", None)
            if old_thread is not None and old_thread.is_alive():
                get_logger().log("  🎬 [컷 경계] 이미 자동 분석이 진행 중입니다")
                return []

            def _worker():
                try:
                    self._auto_scan_cut_boundaries_for_start_sync(project_path, list(files or []))
                except Exception as exc:
                    try:
                        get_logger().log(f"  ⚠️ [컷 경계] 백그라운드 자동 분석 실패: {exc}")
                    except Exception:
                        pass

            thread = threading.Thread(
                target=_worker,
                name="cut-boundary-prescan-worker",
                daemon=True,
            )
            self._cut_boundary_prescan_thread = thread
            thread.start()
            get_logger().log("  🎬 [컷 경계] 백그라운드 자동 분석 시작")
            return []
        except Exception as exc:
            get_logger().log(f"  ⚠️ [컷 경계] 백그라운드 자동 분석 시작 실패: {exc}")
            return []

    def _auto_scan_cut_boundaries_for_start_sync(self, project_path: str, files: list[str]) -> list[dict]:
        """Populate project cut boundaries before STT starts when the feature is enabled."""
        try:
            from core.cut_boundary import (
                cut_boundary_enabled,
                detect_media_cut_boundaries,
                normalize_cut_boundaries,
                sync_project_cut_boundaries,
            )

            settings = load_settings()
            if not cut_boundary_enabled(settings):
                get_logger().log("  🎬 [컷 경계] 비활성화되어 있어 분석을 건너뜁니다")
                return []
            if not project_path or not os.path.exists(project_path):
                get_logger().log("  ⚠️ [컷 경계] 프로젝트 경로가 없어 분석을 건너뜁니다")
                return []

            cached = self._load_cut_boundary_cache_for_start(project_path, files, settings)
            if cached:
                return cached

            clip_boundaries = list(getattr(self.ui, "_multiclip_boundaries", []) or [])
            detected: list[dict] = []
            total_files = len(list(files or []))
            step_sec = max(0.25, float(settings.get("scan_cut_auto_sample_step_sec", 1.0) or 1.0))

            # 자동 사전 스캔은 사용자가 다른 버튼을 누를 수 있어야 하므로
            # 전역 scan_active=True 신호를 보내지 않는다.
            # 이 신호는 UI에서 버튼 비활성화/대기 커서를 유발할 수 있다.
            # self._ui_emit("_sig_set_cut_boundary_scan_active", True)

            def _save_detected_now():
                try:
                    with open(project_path, "r", encoding="utf-8") as f:
                        project = json.load(f)
                    project.setdefault("analysis", {})
                    project["analysis"]["cut_boundaries"] = list(detected)
                    sync_project_cut_boundaries(project, settings=settings)
                    with open(project_path, "w", encoding="utf-8") as f:
                        json.dump(project, f, ensure_ascii=False, indent=2)
                except Exception as exc:
                    get_logger().log(f"  ⚠️ [컷 경계] 중간 저장 실패: {exc}")

            def _progress(info: dict):
                try:
                    clip_no = int(info.get("clip_idx", 0) or 0) + 1
                except Exception:
                    clip_no = 1
                pct = int(info.get("percent", 0) or 0)
                ts = float(info.get("timestamp", 0.0) or 0.0)
                dur = float(info.get("duration", 0.0) or 0.0)
                found = int(info.get("detected", 0) or 0)
                next_ts = min(dur, ts + step_sec) if dur > 0.0 else (ts + step_sec)
                get_logger().log(
                    f"  └ [컷 경계] 파일 {clip_no}/{total_files} 스캔 중 {pct}% "
                    f"({ts:.1f}s / {dur:.1f}s, 감지 {found}개)"
                )
                clip_offset = 0.0
                if (clip_no - 1) < len(clip_boundaries):
                    try:
                        clip_offset = float(clip_boundaries[clip_no - 1].get("start", 0.0) or 0.0)
                    except Exception:
                        clip_offset = 0.0
                self._ui_emit("_sig_preview_cut_boundary_scan", clip_offset + ts, clip_offset + next_ts)

            def _found(row: dict, current_rows: list[dict]):
                detected[:] = normalize_cut_boundaries(list(detected) + [dict(row)])
                clip_no = int(row.get("clip_idx", 0) or 0) + 1
                sec = float(row.get("timeline_sec", row.get("time", 0.0)) or 0.0)
                get_logger().log(
                    f"  🎯 [컷 경계] 파일 {clip_no}/{total_files} 경계 감지 "
                    f"{sec:.3f}s (누적 {len(detected)}개)"
                )
                _save_detected_now()

                # 첫 번째 컷 경계가 발견되면 즉시 00:00~첫 경계 구간의
                # "주제없음/컷경계" 중분류 placeholder를 갱신한다.
                self._ui_emit("_sig_refresh_cut_boundary_placeholder")
                try:
                    self._ui_emit("_sig_refresh_cut_boundary_placeholder")
                except Exception:
                    pass

            for idx, path in enumerate(list(files or [])):
                offset = 0.0
                if idx < len(clip_boundaries):
                    try:
                        offset = float(clip_boundaries[idx].get("start", 0.0) or 0.0)
                    except Exception:
                        offset = 0.0
                get_logger().log(
                    f"  🎬 [컷 경계] 파일 {idx + 1}/{total_files} 분석 시작: {os.path.basename(path)} "
                    f"(offset {offset:.1f}s)"
                )
                rows = detect_media_cut_boundaries(
                    path,
                    clip_offset=offset,
                    clip_idx=idx,
                    sample_step_sec=float(settings.get("scan_cut_auto_sample_step_sec", 1.0) or 1.0),
                    threshold=float(settings.get("scan_cut_auto_threshold", settings.get("scan_cut_threshold", 24.0)) or 24.0),
                    progress_callback=_progress,
                    found_callback=_found,
                )
                get_logger().log(
                    f"  ✅ [컷 경계] 파일 {idx + 1}/{total_files} 분석 완료: {os.path.basename(path)} "
                    f"(감지 {len(rows)}개)"
                )
                detected[:] = normalize_cut_boundaries(list(detected) + list(rows))
            _save_detected_now()
            if detected:
                get_logger().log(f"  🎬 [컷 경계] 시작 전 자동 분석 완료 ({len(detected)}개)")
            else:
                get_logger().log("  🎬 [컷 경계] 시작 전 자동 분석 완료 (감지 없음)")
            return detected
        except Exception as exc:
            get_logger().log(f"  ⚠️ [컷 경계] 시작 전 자동 분석 실패: {exc}")
            return []
        finally:
            self._ui_emit("_sig_set_cut_boundary_scan_active", False)

    def _split_by_saved_cut_boundaries(self, segments, *, offset: float = 0.0, context: str = "자막") -> list[dict]:
        """Split subtitle/STT rows so no row crosses a saved visual cut."""
        try:
            from core.cut_boundary import cut_boundary_enabled, split_segments_by_cut_boundaries

            settings = load_settings()
            boundaries = self._project_cut_boundaries_for_pipeline()
            if offset:
                local = []
                offset = float(offset or 0.0)
                for item in boundaries:
                    row = dict(item)
                    sec = float(row.get("timeline_sec", row.get("time", 0.0)) or 0.0) - offset
                    if sec > 0.0:
                        row["timeline_sec"] = sec
                        row["time"] = sec
                    local.append(row)
                boundaries = local
            if not boundaries:
                return [dict(seg) for seg in (segments or [])]
            result = split_segments_by_cut_boundaries(
                segments,
                boundaries,
                enabled=cut_boundary_enabled(settings),
            )
            if len(result) != len(segments or []):
                get_logger().log(f"  ✂️ [컷 경계] {context} {len(segments or [])}개 → {len(result)}개 절대 분할")
            return result
        except Exception as exc:
            get_logger().log(f"  ⚠️ [컷 경계] {context} 분할 실패, 기존 세그먼트 유지: {exc}")
            return [dict(seg) for seg in (segments or [])]

    def _ask_single_existing_subtitle(self, target_file) -> bool:
        """단일 클립에 기존 SRT가 있으면 사용 여부를 묻고, 미사용 시 백업 이동합니다."""
        try:
            from core.path_manager import get_srt_path
            from core.subtitle_existing import backup_existing_srt, validate_srt_duration
            from ui.dialogs.message_box import ask_yes_no, show_message
            from PyQt6.QtWidgets import QMessageBox

            srt_p = get_srt_path(target_file)
            if not srt_p or not os.path.exists(srt_p):
                return False

            ok, reason = validate_srt_duration(srt_p, target_file)
            if not ok:
                show_message(
                    self.ui,
                    "기존 자막 오류",
                    reason,
                    icon=QMessageBox.Icon.Warning,
                    buttons=QMessageBox.StandardButton.Ok,
                    default=QMessageBox.StandardButton.Ok,
                )
                backup_existing_srt(srt_p)
                return False

            use_existing = ask_yes_no(
                self.ui,
                "기존 자막 사용",
                "기존 자막을 사용하시겠습니까?",
            )
            if not use_existing:
                backup_existing_srt(srt_p)
            return use_existing
        except Exception:
            return False

    def _move_existing_srt_to_backup(self, target_file) -> bool:
        """기존 SRT를 자막백업 폴더로 이동합니다."""
        try:
            from core.subtitle_existing import backup_existing_srt
            return backup_existing_srt(target_file)
        except Exception as e:
            get_logger().log(f"⚠️ 기존 자막 백업 이동 실패: {e}")
            return False

    # ─── 백업 ────────────────────────────────────────────
    def _backup_existing(self, target_file):
        """기존 자막/MOV 파일 백업"""
        try:
            from core.path_manager import get_srt_path
            import datetime
            import shutil

            base_path = os.path.splitext(target_file)[0]
            srt_p = get_srt_path(target_file)
            mov_p = f"{base_path}_자막소스.mov"
            backup_dir = os.path.join(os.path.dirname(target_file), "자막백업")

            if os.path.exists(srt_p) or os.path.exists(mov_p):
                os.makedirs(backup_dir, exist_ok=True)
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                if os.path.exists(srt_p):
                    shutil.copy2(
                        srt_p,
                        os.path.join(backup_dir, f"{os.path.basename(srt_p)}.{timestamp}.bak"),
                    )
                if os.path.exists(mov_p):
                    shutil.copy2(
                        mov_p,
                        os.path.join(backup_dir, f"{os.path.basename(mov_p)}.{timestamp}.bak"),
                    )
                get_logger().log("📦 기존 자막 파일을 '자막백업' 폴더에 안전하게 복사(백업)했습니다.")
        except Exception as e:
            get_logger().log(f"⚠️ 백업 중 오류 발생 (무시하고 진행): {e}")

    # ─── 재시작 ──────────────────────────────────────────
    def _handle_restart(self, target_file):
        """재시작 시 에디터/SRT 초기화"""
        get_logger().log("\n🔄 현재 파일의 자막 생성을 처음부터 다시 시작합니다...")
        try:
            from core.path_manager import get_srt_path

            srt_p = get_srt_path(target_file)
            if os.path.exists(srt_p):
                moved = self._move_existing_srt_to_backup(target_file)
                if moved:
                    get_logger().log("    └ 📦 기존 자막 파일을 백업 후 제거했습니다. (새로 생성)")
                elif os.path.exists(srt_p):
                    os.remove(srt_p)
                    get_logger().log("    └ 🗑️ 기존 자막 파일을 삭제했습니다. (새로 생성)")

            def _clear_editor_main():
                ed = getattr(self.ui, "_editor_widget", None)
                if ed is None:
                    return
                try:
                    if hasattr(ed, "text_edit"):
                        ed.text_edit.blockSignals(True)
                        ed.text_edit.clear()
                        ed.text_edit.blockSignals(False)
                    if hasattr(ed, "timeline") and hasattr(ed.timeline, "canvas"):
                        ed.timeline.update_segments([], 0.0, getattr(ed.timeline.canvas, "total_duration", 0.0))
                        ed.timeline.set_playhead(0.0)
                    if hasattr(ed, "video_player"):
                        ed.video_player.set_context_segments([])
                        ed.video_player.seek(0.0)
                    if hasattr(ed, "_segment_queue"):
                        ed._segment_queue.clear()
                    ed._cached_segs = []
                    ed._active_seg_start = 0.0
                    ed._is_dirty = False
                except Exception as ex:
                    get_logger().log(f"    └ ⚠️ 에디터 초기화 중 오류: {ex}")

            from PyQt6.QtCore import QTimer as _QT

            _QT.singleShot(0, _clear_editor_main)
        except Exception as e:
            get_logger().log(f"    └ ⚠️ 초기화 중 오류: {e}")

    # ─── 저장 + 내보내기 ─────────────────────────────────
    def _save_and_export(self, target_file, queue_index, final_segments, is_auto_mode):
        """SRT 저장 + MOV 렌더링 + 완료 처리"""
        get_logger().log("\n  [STEP 5] 💾 SRT 저장 중...")
        try:
            from core.engine.subtitle_engine import save_srt
            from core.path_manager import get_srt_path

            srt_path = get_srt_path(target_file)
            save_srt(final_segments, srt_path, apply_offset=True)
            get_logger().log(f"✅ {os.path.basename(srt_path)} 저장 완료")

            is_video_export = False
            export_settings = {}
            try:
                try:
                    from ui.dialogs.export_dialog import _load_es
                except ImportError:
                    from ui.dialogs.export_dialog import _load_es
                export_settings = _load_es()
                is_video_export = export_settings.get("icloud", False)
            except Exception:
                pass

            base_name = os.path.splitext(os.path.basename(target_file))[0]
            current_idx = queue_index + 1
            total_cnt = len(self.files_to_process)

            if not is_video_export and getattr(self.ui, "_is_auto_pipeline", False):
                self._send_ntfy_notification(
                    title=f"📝 {config.APP_NAME} 알림",
                    message=f"[{current_idx}/{total_cnt}] {base_name}.srt 생성 완료!\n🎯 다음 작업으로 넘어갑니다.",
                    tags="memo,sparkles",
                )

            if hasattr(self.ui, "_sig_update_queue"):
                try:
                    self.ui._sig_update_queue.emit(queue_index, "✅ 자막출력(srt)", "", "", "")
                except RuntimeError:
                    pass

            # ── STEP 6: MOV 렌더링 ──
            if is_video_export:
                try:
                    get_logger().log(
                        "\n  [STEP 6] 🎥 투명 자막 영상(MOV) 백그라운드 렌더링 및 iCloud 백업 중..."
                    )
                    if hasattr(self.ui, "_sig_update_queue"):
                        self.ui._sig_update_queue.emit(
                            queue_index, "🎥 자막영상출력(mov)", "", "", ""
                        )
                    self._run_background_render(
                        srt_path, target_file, export_settings, current_idx, total_cnt
                    )
                except Exception as e:
                    get_logger().log(f"❌ MOV 렌더링 오류: {e}")
                    get_logger().log(traceback.format_exc())

            try:
                from core.auto_tracker import AutoTracker

                AutoTracker().mark_completed(target_file)
                if hasattr(self.ui, "mark_cloud_file_done"):
                    self.ui.mark_cloud_file_done(target_file)
            except Exception:
                pass

            if hasattr(self.ui, "_sig_update_queue"):
                try:
                    if is_auto_mode:
                        self.ui._sig_update_queue.emit(
                            queue_index, "완료 (다음파일)", "", "", ""
                        )
                    else:
                        self.ui._sig_update_queue.emit(
                            queue_index, "자막생성완료", "", "", ""
                        )
                except RuntimeError:
                    pass

        except Exception as e:
            get_logger().log(f"❌ 처리 실패: {e}")

    # ─── 렌더링 ──────────────────────────────────────────
    def _run_background_render(self, srt_path, target_file, s, current_idx=1, total_cnt=1):
        """MOV 렌더링 → renderer.py에 위임"""
        from core.renderer import render_subtitle_mov

        success = render_subtitle_mov(srt_path, target_file, s, current_idx, total_cnt)

        if success:
            base_name = os.path.splitext(os.path.basename(target_file))[0]
            if getattr(self.ui, "_is_auto_pipeline", False):
                self._send_ntfy_notification(
                    title=f"🎞️ {config.APP_NAME} 알림",
                    message=f"[{current_idx}/{total_cnt}] {base_name}.srt / {base_name}.mov 생성 완료!",
                    tags="film_projector,rocket",
                )

        return success

    # ─── 화자 분리 ───────────────────────────────────────
    def _reload_speaker_settings(self):
        s = load_settings()
        self.min_speakers = int(s.get("min_speakers", 1))
        self.max_speakers = int(s.get("max_speakers", 1))

    def _load_selected_model(self):
        s = load_settings()
        return s.get("selected_model", getattr(config, "OLLAMA_MODEL", "exaone3.5:7.8b"))

    def _prepare_speaker_map(self, audio_path):
        try:
            from core.audio.diarize import get_speaker_map

            self._speaker_map = get_speaker_map(
                audio_path, self.min_speakers, self.max_speakers
            )
        except Exception:
            self._speaker_map = []

    # ─── NTFY 알림 ───────────────────────────────────────
    def _send_ntfy_notification(self, title, message, tags=""):
        from core.notifier import send_ntfy

        send_ntfy(title, message, tags)

    # ─── 프리페치 ────────────────────────────────────────
    def _prefetch_audio_for_file(self, target_file):
        if not target_file or not self._active:
            return

        current_generation = self._prefetch_generation

        with self._prefetch_lock:
            if target_file in self._prefetch_cache:
                return
            if target_file in self._prefetch_threads:
                th = self._prefetch_threads[target_file]
                if th.is_alive():
                    return

        def _task():
            vp = VideoProcessor()
            try:
                res = vp.extract_audio(target_file)
                with self._prefetch_lock:
                    if current_generation == self._prefetch_generation:
                        self._prefetch_cache[target_file] = res
            except Exception as e:
                get_logger().log(
                    f"⚠️ 오디오 선추출 실패: {os.path.basename(target_file)} / {e}"
                )
                with self._prefetch_lock:
                    if current_generation == self._prefetch_generation:
                        self._prefetch_cache[target_file] = None
            finally:
                try:
                    vp.stop_transcribe()
                except Exception:
                    pass
                with self._prefetch_lock:
                    self._prefetch_threads.pop(target_file, None)

        th = threading.Thread(
            target=_task,
            daemon=True,
            name=f"prefetch-{os.path.basename(target_file)}",
        )
        with self._prefetch_lock:
            self._prefetch_threads[target_file] = th
        th.start()

    # ─── 오디오 추출 결과 ────────────────────────────────
    def _get_audio_extract_result(self, target_file):
        th = None
        with self._prefetch_lock:
            th = self._prefetch_threads.get(target_file)

        if th and th.is_alive():
            th.join()

        with self._prefetch_lock:
            cached = self._prefetch_cache.pop(target_file, None)

        if cached:
            return cached

        return self.video_processor.extract_audio(target_file)
