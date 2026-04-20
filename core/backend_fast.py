# Version: 02.02.00
# Phase: PHASE1-B
"""
core/backend_fast.py
멀티 클립 배치 전용 파이프라인
- CoreBackend를 상속하여 단일 파일 로직 재사용
- 멀티 파일: 자동 시작 + SRT 개별 저장 + 큐 순차 처리
- 단일 파일과의 차이: 에디터 대기 없이 자동 진행
"""
import os, threading, time
import config
from logger import get_logger
from .backend import CoreBackend
from .settings import load_settings, get_model_key
from .time_history import get_expected_time, add_history


class CoreBackendFast(CoreBackend):
    """
    멀티 클립 배치 모드 전용.
    - start_pipeline()에서 is_auto_start=True로 호출
    - 에디터 편집 대기 없이 STT → SRT 저장 자동 진행
    """

    def start_batch(self, files, folder=None):
        """멀티 파일 배치 시작 (자동 모드 강제)"""
        if not files:
            return
        get_logger().log(f"⚡ 배치 모드: {len(files)}개 파일 자동 처리 시작")
        self.start_pipeline(files, folder=folder, is_auto_start=True)

    def _process_one_fast(self, target_file, queue_index):
        """
        단일 파일 고속 처리 (에디터 대기 없음)
        - 오디오 추출 → STT → SRT 저장 → 다음 파일
        """
        vname = os.path.basename(target_file)
        fsize = os.path.getsize(target_file) / (1024 * 1024) if os.path.exists(target_file) else 0

        get_logger().log(
            f"\n{'=' * 44}\n"
            f"⚡ [{queue_index + 1}/{len(self.files_to_process)}] {vname}\n"
            f"{'=' * 44}\n"
            f"  📂 파일: {vname} ({fsize:.1f} MB)"
        )

        # ── STEP 0: 백업 ──
        self._backup_existing(target_file)

        # ── STEP 1: 오디오 추출 ──
        if hasattr(self.ui, '_sig_update_queue'):
            self.ui._sig_update_queue.emit(queue_index, "⏳ 오디오 추출 중", "", "", "")

        res = self.video_processor.extract_audio(target_file)
        if not res:
            get_logger().log(f"❌ 오디오 추출 실패: {vname}")
            if hasattr(self.ui, '_sig_update_queue'):
                self.ui._sig_update_queue.emit(queue_index, "❌ 추출 실패", "", "", "")
            return False

        chunk_dir, vad_segs = res
        if hasattr(self.ui, '_sig_set_vad_segments'):
            self.ui._sig_set_vad_segments.emit(vad_segs)

        # ── STEP 2: ETA 계산 + STT 시작 ──
        try:
            s = load_settings()
            model_key = get_model_key(s)

            if target_file in getattr(self, '_video_durations', {}):
                video_duration_sec = self._video_durations[target_file]
            else:
                chunks = [f for f in os.listdir(chunk_dir) if f.endswith('.wav')]
                video_duration_sec = len(chunks) * 30.0

            expected_time = get_expected_time(model_key, video_duration_sec)
            if hasattr(self.ui, '_sig_update_queue'):
                eta_str = str(expected_time) if expected_time > 0 else "예상불가"
                self.ui._sig_update_queue.emit(queue_index, "⚡ 자막 생성 중", eta_str, "", "")
            process_start_time = time.time()
        except Exception:
            process_start_time = time.time()
            video_duration_sec = 0.0

        # ── STEP 3: Whisper + LLM (동기 실행) ──
        import queue as _queue
        from .subtitle_engine import optimize_segments

        _SENTINEL = object()
        opt_queue = _queue.Queue()
        all_segments = []

        def do_transcribe():
            try:
                for chunk_segs, c_idx, t_total in self.video_processor.transcribe(chunk_dir, is_fast_mode=True):
                    if not self._active:
                        break
                    opt_queue.put((chunk_segs, c_idx, t_total))
            finally:
                opt_queue.put(_SENTINEL)

        def do_optimize():
            try:
                s = load_settings()
                chunk_time_limit = int(s.get('chunk_time_limit', 60))
            except Exception:
                chunk_time_limit = 60

            seg_buffer = []
            last_c_idx = 0
            last_t_total = 1

            def _flush():
                nonlocal seg_buffer
                if not seg_buffer:
                    return
                chunk_segs = seg_buffer
                seg_buffer = []
                try:
                    opt = optimize_segments(chunk_segs)
                except Exception:
                    opt = chunk_segs

                for seg in opt:
                    if seg["start"] < 0.0:
                        seg["start"] = 0.0
                    if seg["end"] <= seg["start"]:
                        seg["end"] = seg["start"] + 0.5

                all_segments.extend(opt)

                if hasattr(self.ui, "_sig_append_segments"):
                    self.ui._sig_append_segments.emit(opt)

            while self._active:
                item = opt_queue.get()
                if item is _SENTINEL:
                    _flush()
                    break

                chunk_segs, c_idx, t_total = item
                last_c_idx = c_idx
                last_t_total = t_total

                total_files = len(self.files_to_process)
                if t_total > 0:
                    pct = int(((queue_index + (c_idx / t_total)) / total_files) * 100)
                else:
                    pct = int((queue_index / total_files) * 100)

                if hasattr(self.ui, '_sig_update_queue_header'):
                    self.ui._sig_update_queue_header.emit(queue_index + 1, total_files, pct, "")

                if not chunk_segs:
                    if hasattr(self.ui, '_sig_update_status'):
                        self.ui._sig_update_status.emit(c_idx, t_total)
                    continue

                seg_buffer.extend(chunk_segs)
                if seg_buffer:
                    dur = seg_buffer[-1]["end"] - seg_buffer[0]["start"]
                    if dur >= chunk_time_limit:
                        _flush()

            # 완료 시그널
            if hasattr(self.ui, '_sig_update_status'):
                self.ui._sig_update_status.emit(last_t_total, last_t_total)

        t1 = threading.Thread(target=do_transcribe, daemon=True, name="fast-transcriber")
        t2 = threading.Thread(target=do_optimize, daemon=True, name="fast-optimizer")
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # ── 큐 즉시 업데이트 ──
        if hasattr(self.ui, '_sig_update_queue'):
            try:
                self.ui._sig_update_queue.emit(queue_index, "✅ 자막 생성 완료", "완료", "", "")
            except RuntimeError:
                pass

        # ── 히스토리 기록 ──
        try:
            model_key = get_model_key()
            proc_time = time.time() - process_start_time
            add_history(model_key, video_duration_sec, proc_time)
        except Exception:
            pass

        # ── STEP 5~6: SRT 저장 + 내보내기 ──
        self._save_and_export(target_file, queue_index, all_segments, is_auto_mode=True)

        return True

    def _run_all(self):
        """배치 모드 전용 _run_all: 에디터 대기 없이 순차 처리"""
        eta_thread = getattr(self, '_eta_thread', None)
        if eta_thread and eta_thread.is_alive():
            eta_thread.join(timeout=30)

        try:
            total_files = len(self.files_to_process)
            success_count = 0

            for i, target_file in enumerate(self.files_to_process):
                if not self._active:
                    return

                if hasattr(self.ui, '_sig_update_queue_header'):
                    self.ui._sig_update_queue_header.emit(i + 1, total_files, 0, "")

                ok = self._process_one_fast(target_file, i)
                if ok:
                    success_count += 1

            if getattr(self.ui, '_is_auto_pipeline', False):
                self._send_ntfy_notification(
                    title=f"🏆 {config.APP_NAME} 배치 완료",
                    message=f"🎉 {success_count}/{total_files}개 파일 처리 완료!",
                    tags="checkered_flag,tada"
                )

        except Exception as e:
            if str(e) not in ("USER_PREV", "USER_EXIT"):
                get_logger().log(f"\n❌ 배치 치명적 에러: {e}")
                import traceback
                get_logger().log(traceback.format_exc())

        finally:
            self._active = False
            try:
                if hasattr(self.ui, 'request_show_home'):
                    self.ui.request_show_home()
            except Exception:
                pass