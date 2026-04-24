# Version: 02.02.01
# Phase: PHASE1-B
"""
core/pipeline/pipeline_helpers.py
PipelineHelpersMixin — 백업 · 재시작 · 저장/내보내기 · 렌더링 · 화자분리 · ntfy · 프리페치 · 오디오 추출
"""
import os
import threading
import traceback
import time

import config
from logger import get_logger
from core.audio.media_processor import VideoProcessor
from core.settings import load_settings, get_model_key


class PipelineHelpersMixin:
    """CoreBackend 에서 사용하는 공통 헬퍼 메서드 모음."""

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
                        ed.timeline.canvas.segments.clear()
                        ed.timeline.canvas.update()
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
                            queue_index, "✅ 완료 (다음파일)", "", "", ""
                        )
                    else:
                        self.ui._sig_update_queue.emit(
                            queue_index, "✅ 자막생성완료", "", "", ""
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
