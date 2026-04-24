# Version: 02.02.01
# Phase: PHASE1-B
"""
core/pipeline/multiclip_pipeline.py
MulticlipPipelineMixin — 멀티클립 품질모드 파이프라인 (start_multiclip_pipeline, _run_multiclip)
"""
import os
import threading
import traceback
import time

import config
from logger import get_logger
from core.settings import load_settings, get_model_key
from core.time_history import get_expected_time
from core.media_info import probe_media


class MulticlipPipelineMixin:
    """멀티클립 품질모드: 모든 클립 순차 STT → 하나의 에디터에서 편집."""

    def start_multiclip_pipeline(self, files, folder=None):
        """멀티클립 품질모드 진입점"""
        self._active = True
        self.files_to_process = list(files)
        self.current_folder = folder
        self.is_auto_start = False
        self.is_first_start = True
        self.total_expected_time = 0.0
        self.pipeline_start_time = 0.0
        self._reuse_existing_multiclip_subtitles = False

        try:
            from PyQt6.QtWidgets import QMessageBox
            candidates = []
            for _f in self.files_to_process:
                if os.path.exists(os.path.splitext(_f)[0] + '.srt'):
                    candidates.append(_f)
            if candidates:
                self._reuse_existing_multiclip_subtitles = QMessageBox.question(
                    self.ui, '기존 자막 사용', '기존 자막을 사용하겠습니까?'
                ) == QMessageBox.StandardButton.Yes
        except Exception:
            self._reuse_existing_multiclip_subtitles = False

        with self._prefetch_lock:
            self._prefetch_generation += 1
            self._prefetch_cache = {}
            self._prefetch_threads = {}

        if not self.files_to_process:
            return
        if hasattr(self.ui, "init_queue_list"):
            self.ui.init_queue_list(self.files_to_process)

        get_logger().log(
            f"🎬 멀티클립 품질모드: {len(self.files_to_process)}개 클립 순차 처리"
        )
        self._pipeline_thread = threading.Thread(
            target=self._run_multiclip, daemon=True, name="multiclip-main"
        )
        self._pipeline_thread.start()

    def _run_multiclip(self):
        try:
            total_files = len(self.files_to_process)
            first_file = self.files_to_process[0]

            # ── STEP 0: 클립 길이 사전 계산 ──
            get_logger().log(f"🎬 멀티클립: {total_files}개 클립 정보 수집 중...")

            # Queue UI was already initialized on the main thread in
            # start_multiclip_pipeline(); do not touch QWidget/timers here.
            clip_boundaries = []
            failed_clips = []
            cumulative = 0.0
            s = load_settings()
            model_key = get_model_key(s)
            total_expected = 0.0

            for i, target_file in enumerate(self.files_to_process):
                vname = os.path.basename(target_file)
                try:
                    info = probe_media(target_file)
                    clip_dur = info["duration"]
                    info_txt = info["info_txt"]
                    len_txt = info["len_txt"]

                    expected = get_expected_time(model_key, clip_dur)
                    if expected > 0:
                        total_expected += expected

                    if hasattr(self.ui, "_sig_update_queue"):
                        self.ui._sig_update_queue.emit(
                            i, "⏳ 대기 중", str(expected), info_txt, len_txt
                        )
                except Exception:
                    clip_dur = 30.0
                    info_txt = ""
                    len_txt = ""

                clip_boundaries.append(
                    {
                        "start": cumulative,
                        "end": cumulative + clip_dur,
                        "file": target_file,
                        "name": vname,
                    }
                )
                cumulative += clip_dur
                get_logger().log(
                    f"  📂 [{i + 1}/{total_files}] {vname}: {clip_dur:.1f}초"
                )

            self.total_expected_time = total_expected
            if total_expected > 0 and hasattr(self.ui, "_sig_update_queue_header"):
                t_mins, t_secs = int(total_expected // 60), int(total_expected % 60)
                t_hours = t_mins // 60
                if t_hours > 0:
                    t_mins = t_mins % 60
                    total_str = f"{t_hours}시간 {t_mins}분 {t_secs}초"
                else:
                    total_str = f"{t_mins}분 {t_secs}초"

                self.ui._sig_update_queue_header.emit(1, total_files, 0, total_str)

            # 멀티클립 경계 정보를 UI에 전달 (에디터 열기 전)
            self.ui._multiclip_boundaries = clip_boundaries

            # ── STEP 1: 에디터 열기 (클립 박스만 표시, 파형 아직 없음) ──
            edit_event = threading.Event()
            start_event = threading.Event()
            self._edit_event = edit_event
            self._start_event = start_event
            final_segments = []
            action_state = ["wait"]
            self._action_state = action_state

            def on_save(segs):
                nonlocal final_segments
                final_segments = segs
                action_state[0] = "next"
                edit_event.set()

            def on_start():
                if getattr(self, "is_first_start", True):
                    self.pipeline_start_time = time.time()
                    self.is_first_start = False
                action_state[0] = "start"
                start_event.set()

            def on_prev():
                action_state[0] = "prev"
                start_event.set()
                edit_event.set()

            def on_exit(segs):
                nonlocal final_segments
                final_segments = segs
                action_state[0] = "exit"
                self.stop()
                start_event.set()
                edit_event.set()

            self.ui.open_editor_for_file(
                first_file, on_save, on_start, on_prev, on_exit, is_batch=False
            )

            # ── 멀티클립 파형 로드 시작 (에디터 열린 직후) ──
            if hasattr(self.ui, "_sig_load_multiclip_waveform"):
                self.ui._sig_load_multiclip_waveform.emit(clip_boundaries)

            # 시작 버튼 대기
            if not start_event.wait(timeout=600):
                get_logger().log("❌ 시작 이벤트 타임아웃")
                return

            if action_state[0] in ("prev", "exit"):
                self.ui.request_show_home()
                return

            # ── STEP 2: 클립별 오디오 추출 + Whisper (순차) ──
            get_logger().log("\n🎤 멀티클립 STT 시작...")

            for i, target_file in enumerate(self.files_to_process):
                if not self._active:
                    return

                # 기존 자막으로 이미 사전 로드된 클립은 skip
                if getattr(self, '_reuse_existing_multiclip_subtitles', False) and i in locals().get('_reuse_done', set()):
                    continue

                vname = os.path.basename(target_file)
                bd = clip_boundaries[i]
                offset = bd["start"]

                get_logger().log(
                    f"\n{'=' * 44}\n🎬 [{i + 1}/{total_files}] {vname}\n{'=' * 44}"
                )

                if hasattr(self.ui, "_sig_update_queue"):
                    self.ui._sig_update_queue.emit(i, "⏳ 오디오 추출 중", "", "", "")

                if getattr(self, "_reuse_existing_multiclip_subtitles", False):
                    existing_srt = os.path.splitext(target_file)[0] + ".srt"
                    if os.path.exists(existing_srt):
                        try:
                            from core.srt_parser import parse_srt
                            clip_segments = parse_srt(existing_srt)
                            if clip_segments:
                                for seg in clip_segments:
                                    seg["start"] = float(seg.get("start", 0.0)) + offset
                                    seg["end"] = float(seg.get("end", 0.0)) + offset
                                    seg["_clip_idx"] = i
                                    if "speaker" not in seg:
                                        seg["speaker"] = seg.get("spk_id", "00")
                                if hasattr(self.ui, "_sig_append_segments"):
                                    self.ui._sig_append_segments.emit(clip_segments)
                                if hasattr(self.ui, "_sig_update_queue"):
                                    self.ui._sig_update_queue.emit(i, "✅기존자막", " - ", "", "")
                                get_logger().log(f"  ✅ 기존 자막 사용: {vname} ({len(clip_segments)}개 세그먼트)")
                                continue
                            else:
                                get_logger().log(f"  ⚠️ 기존 자막 파일이 비어있음: {vname}")
                        except Exception as e:
                            get_logger().log(f"  ⚠️ 기존 자막 로드 실패: {vname} / {e}")

                self._backup_existing(target_file)
                res = self._get_audio_extract_result(target_file)

                next_file = (
                    self.files_to_process[i + 1] if (i + 1) < total_files else None
                )
                if next_file:
                    self._prefetch_audio_for_file(next_file)

                if not res:
                    get_logger().log(f"  ❌ 오디오 추출 실패: {vname}")
                    if hasattr(self.ui, "_sig_update_queue"):
                        self.ui._sig_update_queue.emit(i, "❌ 오류", "", "", "")
                    continue

                chunk_dir, vad_segs = res

                # ── 멀티클립 VAD 그린존 전달 ──
                if hasattr(self.ui, "_current_file_idx"):
                    self.ui._current_file_idx = i + 1  # 1-based
                if hasattr(self.ui, "_sig_set_vad_segments"):
                    self.ui._sig_set_vad_segments.emit(vad_segs)

                # ── Whisper 인식 존 설정 (그린→옐로우 진행) ──
                if hasattr(self.ui, "_sig_set_recog_zone"):
                    self.ui._sig_set_recog_zone.emit(offset, bd["end"])

                if hasattr(self.ui, "_sig_update_queue"):
                    self.ui._sig_update_queue.emit(i, "⏳ 자막 생성 중", "", "", "")

                get_logger().log("  🎤 Whisper 변환 중...")

                # ── Whisper transcribe (단일 루프) ──
                clip_segments = []
                for chunk_segs, c_idx, t_total in self.video_processor.transcribe(
                    chunk_dir
                ):
                    if not self._active:
                        return
                    clip_segments.extend(chunk_segs)
                    # ── 옐로우존 진행률 업데이트 ──
                    if chunk_segs and hasattr(self.ui, "_sig_set_recog_progress"):
                        last_end = max(seg["end"] for seg in chunk_segs) + offset
                        self.ui._sig_set_recog_progress.emit(last_end)

                get_logger().log(f"    📊 총 {len(clip_segments)}개 세그먼트")

                # 시간 오프셋 적용
                for seg in clip_segments:
                    seg["start"] += offset
                    seg["end"] += offset
                    seg["_clip_idx"] = i
                    if "words" in seg:
                        for w in seg["words"]:
                            w["start"] += offset
                            w["end"] += offset

                # 최적화
                from core.engine.subtitle_engine import optimize_segments

                opt = optimize_segments(clip_segments)
                for seg in opt:
                    if seg["start"] < 0.0:
                        seg["start"] = 0.0
                    if seg["end"] <= seg["start"]:
                        seg["end"] = seg["start"] + 0.5
                    seg["_clip_idx"] = i

                # 에디터에 즉시 전달 (클립 완료될 때마다)
                if hasattr(self.ui, "_sig_append_segments"):
                    self.ui._sig_append_segments.emit(opt)

                # ── 클립 완료 → 인식 존 클리어 ──
                if hasattr(self.ui, "_sig_set_recog_zone"):
                    self.ui._sig_set_recog_zone.emit(-1.0, -1.0)

                if hasattr(self.ui, "_sig_update_queue"):
                    self.ui._sig_update_queue.emit(i, "✅ 완료", "", "", "")

                get_logger().log(
                    f"  ✅ 클립 {i + 1} 자막 완료 ({len(opt)}개 세그먼트)"
                )

            get_logger().log(
                f"\n🎊 전체 {total_files}개 클립 처리 완료! 에디터에서 편집 후 저장하세요."
            )

            if hasattr(self.ui, "_sig_update_status"):
                self.ui._sig_update_status.emit(total_files, total_files)

            # ── 편집 대기 ──
            edit_event.wait()

            if action_state[0] == "exit" or not self._active:
                self.ui.request_show_home()
                return

            # ── 통합 SRT 저장 ──
            if final_segments:
                from core.engine.subtitle_engine import save_srt
                from core.path_manager import get_srt_path

                srt_path = get_srt_path(first_file)
                save_srt(final_segments, srt_path, apply_offset=True)
                get_logger().log(
                    f"✅ {os.path.basename(srt_path)} 저장 완료 (멀티클립 통합)"
                )

        except Exception as e:
            if str(e) not in ("USER_PREV", "USER_EXIT"):
                try:
                    if hasattr(self.ui, "_sig_update_queue") and "i" in locals():
                        self.ui._sig_update_queue.emit(i, "오류", str(e), "", "")
                except Exception:
                    pass
                get_logger().log(f"\n❌ 치명적 에러: {e}")
                get_logger().log(traceback.format_exc())
        finally:
            self._active = False
