# Version: 03.14.34
# Phase: PHASE1-B
"""
core/pipeline/pipeline_helpers.py
PipelineHelpersMixin — VAD 정렬 · 백업 · 재시작 · 저장/내보내기 · 렌더링 · 화자분리 · ntfy · 프리페치 · 오디오 추출
"""
import os
import threading
import traceback

from core.runtime import config
from core.runtime.logger import get_logger
from core.audio.media_processor import VideoProcessor
from core.settings import load_settings
from core.pipeline.cut_boundary_helpers import PipelineCutBoundaryMixin


class PipelineHelpersMixin(PipelineCutBoundaryMixin):
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
    def _emit_queue_status(self, queue_index, status, time_txt="", info_txt="", len_txt=""):
        if hasattr(self.ui, "_sig_update_queue"):
            try:
                self.ui._sig_update_queue.emit(queue_index, status, time_txt, info_txt, len_txt)
            except RuntimeError:
                pass

    def _save_project_for_queue_clip(self, target_file, srt_path, final_segments):
        from core.project.project_manager import create_project, save_project
        from core.work_mode import EDITOR_MODE

        ui = getattr(self, "ui", None)
        editor = getattr(ui, "_editor_widget", None) if ui is not None else None
        project_path = str(getattr(ui, "_current_project_path", "") or "") if ui is not None else ""
        settings = dict(getattr(editor, "settings", {}) or {})
        if not project_path:
            base_name = os.path.splitext(os.path.basename(target_file))[0]
            project_path = create_project(
                name=base_name,
                media_paths=[target_file],
                srt_path=srt_path,
                user_settings=settings,
            )
            if ui is not None:
                ui._current_project_path = project_path

        workspace = {
            "last_playhead": 0.0,
            "last_cursor_block": 0,
            "active_clip_idx": 0,
            "active_work_mode": EDITOR_MODE,
        }
        try:
            if editor is not None and hasattr(editor, "video_player"):
                workspace["last_playhead"] = float(getattr(editor.video_player, "current_time", 0.0) or 0.0)
            if editor is not None and hasattr(editor, "text_edit"):
                workspace["last_cursor_block"] = int(editor.text_edit.textCursor().blockNumber())
        except Exception:
            pass

        save_project(
            filepath=project_path,
            media_paths=[target_file],
            srt_path=srt_path,
            segments=list(final_segments or []),
            user_settings=settings,
            workspace=workspace,
            active_work_mode=EDITOR_MODE,
            voice_activity_segments=[],
            stt_preview_segments=[],
            provisional_cut_boundaries=[],
        )
        return project_path

    def _save_and_export(self, target_file, queue_index, final_segments, is_auto_mode):
        """SRT 저장 + MOV 렌더링 + 완료 처리"""
        get_logger().log("\n  [STEP 5] 💾 SRT 저장 중...")
        try:
            from core.engine.subtitle_engine import save_srt
            from core.path_manager import get_srt_path

            srt_path = get_srt_path(target_file)
            self._emit_queue_status(queue_index, "💾 SRT 저장 중", "", "", "")
            save_srt(final_segments, srt_path, apply_offset=True)
            get_logger().log(f"✅ {os.path.basename(srt_path)} 저장 완료")

            self._emit_queue_status(queue_index, "📦 프로젝트 저장 중", "", "", "")
            project_path = self._save_project_for_queue_clip(target_file, srt_path, final_segments)
            get_logger().log(f"📦 프로젝트 저장 완료: {os.path.basename(project_path)}")

            is_video_export = False
            export_settings = {}
            try:
                try:
                    from ui.dialogs.export_dialog import _load_es
                except ImportError:
                    from ui.dialogs.export_dialog import _load_es
                export_settings = _load_es()
                is_video_export = bool(
                    getattr(self.ui, "_auto_export_subtitle_video", False)
                    or export_settings.get("icloud", False)
                )
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

            self._emit_queue_status(queue_index, "💾 SRT 저장됨", "", "", "")

            # ── STEP 6: MOV 렌더링 ──
            if is_video_export:
                try:
                    get_logger().log(
                        "\n  [STEP 6] 🎥 투명 자막 영상(MOV) 백그라운드 렌더링 중..."
                    )
                    self._emit_queue_status(queue_index, "🎥 자막영상출력(mov)", "", "", "")
                    render_ok = self._run_background_render(
                        srt_path, target_file, export_settings, current_idx, total_cnt
                    )
                    if not render_ok:
                        self._emit_queue_status(queue_index, "❌ 자막영상출력 실패", "", "", "")
                        return False
                except Exception as e:
                    get_logger().log(f"❌ MOV 렌더링 오류: {e}")
                    get_logger().log(traceback.format_exc())
                    self._emit_queue_status(queue_index, "❌ 자막영상출력 실패", "", "", "")
                    return False

            try:
                from core.auto_tracker import AutoTracker

                AutoTracker().mark_completed(target_file)
                if hasattr(self.ui, "mark_cloud_file_done"):
                    self.ui.mark_cloud_file_done(target_file)
            except Exception:
                pass

            self._emit_queue_status(
                queue_index,
                "✅ 완료" if is_auto_mode else "✅ 자막생성완료",
                "",
                "",
                "",
            )
            return True

        except Exception as e:
            get_logger().log(f"❌ 처리 실패: {e}")
            self._emit_queue_status(queue_index, "❌ 저장 실패", "", "", "")
            return False

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
    def _validate_audio_extract_result(self, result, target_file=None, *, context: str = "오디오 추출"):
        """Return a usable audio extraction result only when STT wav chunks exist."""
        if not result:
            return None
        try:
            chunk_dir = result[0]
        except Exception:
            chunk_dir = ""
        try:
            has_chunks = os.path.isdir(chunk_dir) and any(
                str(name).lower().endswith(".wav") for name in os.listdir(chunk_dir)
            )
        except Exception:
            has_chunks = False
        if has_chunks:
            return result

        label = os.path.basename(str(target_file or "")) if target_file else ""
        suffix = f" ({label})" if label else ""
        get_logger().log(f"❌ {context} 실패: 생성된 STT 청크가 없습니다{suffix}")
        return None

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
                tune = self._auto_audio_tune_settings_for_file(target_file)
                if hasattr(vp, "set_auto_audio_tune_overrides"):
                    vp.set_auto_audio_tune_overrides(tune)
                res = self._validate_audio_extract_result(
                    vp.extract_audio(target_file),
                    target_file,
                    context="오디오 선추출",
                )
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

        tune = self._auto_audio_tune_settings_for_file(target_file)
        if hasattr(self.video_processor, "set_auto_audio_tune_overrides"):
            self.video_processor.set_auto_audio_tune_overrides(tune)
        if cached:
            return self._validate_audio_extract_result(cached, target_file)
        return self._validate_audio_extract_result(
            self.video_processor.extract_audio(target_file),
            target_file,
        )

    def _auto_audio_tune_enabled(self) -> bool:
        try:
            settings = load_settings()
            return not bool(settings.get("audio_preset_auto_disabled", False))
        except Exception:
            return True

    def _auto_audio_tune_settings_for_file(self, target_file: str) -> dict:
        if not self._auto_audio_tune_enabled():
            return {}
        target_file = str(target_file or "")
        if not target_file:
            return {}
        cache = getattr(self, "_auto_audio_tune_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._auto_audio_tune_cache = cache
        if target_file in cache:
            return dict(cache.get(target_file) or {})
        try:
            from core.audio.preset_auto_classifier import (
                append_audio_lora_record,
                apply_auto_classified_presets,
                auto_classify_media_presets,
                format_auto_audio_decision_log,
            )

            base_settings = dict(load_settings())
            decision = auto_classify_media_presets(target_file, settings=base_settings)
            updated = apply_auto_classified_presets(base_settings, decision)
            tune = dict(updated.get("audio_preset_auto_tune") or {})
            cache[target_file] = tune
            try:
                append_audio_lora_record(decision, target_file)
            except Exception as record_exc:
                get_logger().log(f"  ⚠️ [오토 오디오] LoRA 누적 기록 실패: {record_exc}")
            get_logger().log(format_auto_audio_decision_log(decision, target_file))
            return tune
        except Exception as exc:
            get_logger().log(f"⚠️ 오디오 자동 튜닝 실패: {os.path.basename(target_file)} / {exc}")
            cache[target_file] = {}
            return {}

from core.pipeline.topicless_segments import install_topicless_segment_helpers

install_topicless_segment_helpers(PipelineHelpersMixin)
