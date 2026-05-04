# Version: 03.14.34
# Phase: PHASE1-B
"""
core/backend_fast.py
자동 배치 전용 파이프라인
- CoreBackend를 상속하여 단일 파일 로직 재사용
- 멀티 파일: 정확도 우선 자동 시작 + SRT 개별 저장 + 큐 순차 처리
- 단일 파일과의 차이: 에디터 대기 없이 자동 진행
"""
import os, threading, time
from core.runtime import config
from core.runtime.logger import get_logger
from .pipeline.backend_core import CoreBackend
from .settings import (
    clear_runtime_settings_override,
    get_model_key,
    load_settings,
    set_runtime_settings_override,
)
from .time_history import get_expected_time, add_history


class CoreBackendFast(CoreBackend):
    """
    자동 배치 모드 전용.
    - start_pipeline()에서 is_auto_start=True로 호출
    - 에디터 편집 대기 없이 STT → SRT 저장 자동 진행
    """

    def __init__(self, main_window):
        super().__init__(main_window)
        # 부모에서 등록한 UI 콜백 중복 방지 — 이미 backend가 등록했으므로 재등록 안 함
        # get_logger().set_ui_callback은 부모에서 이미 호출됨
        # 여기서는 추가 콜백 등록 없이 초기화만 완료

    def start_batch(self, files, folder=None):
        """멀티 파일 정확도 우선 배치 시작 (직접 스레드 관리)."""
        if not files:
            return
        if self._active:
            return

        self._active = True
        set_runtime_settings_override(getattr(self.ui, "_runtime_settings_override", None))
        self.files_to_process = list(files)
        self.current_folder = folder
        self.is_auto_start = True
        self.total_expected_time = 0.0
        self.pipeline_start_time = time.time()
        self.is_first_start = False

        if hasattr(self.ui, 'init_queue_list'):
            self.ui.init_queue_list(self.files_to_process)

        self._video_durations = {}
        self._eta_thread = threading.Thread(target=self._precalculate_etas, daemon=True, name="eta-calculator")
        self._eta_thread.start()

        get_logger().log(f"🎯 정확도 우선 배치: {len(self.files_to_process)}개 파일 자동 처리 시작")

        self._pipeline_thread = threading.Thread(target=self._run_all, daemon=True, name="batch-main")
        self._pipeline_thread.start()

    def _process_one_fast(self, target_file, queue_index):
        """
        단일 파일 정확도 우선 자동 처리 (에디터 대기 없음)
        - 오디오 추출 → STT 앙상블/LLM 검수 → SRT 저장 → 다음 파일
        """
        vname = os.path.basename(target_file)
        fsize = os.path.getsize(target_file) / (1024 * 1024) if os.path.exists(target_file) else 0

        get_logger().log(
            f"\n{'=' * 44}\n"
            f"🎯 [{queue_index + 1}/{len(self.files_to_process)}] {vname}\n"
            f"{'=' * 44}\n"
            f"  📂 파일: {vname} ({fsize:.1f} MB)"
        )

        # ── STEP 0: 백업 ──
        self._backup_existing(target_file)

        # ── STEP 1: 오디오 추출 (클립/청크별 오토 오디오 라우팅 적용) ──
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
            if tune and hasattr(self.video_processor, "set_auto_audio_tune_overrides"):
                self.video_processor.set_auto_audio_tune_overrides(tune)
            try:
                append_audio_lora_record(decision, target_file)
            except Exception as record_exc:
                get_logger().log(f"  ⚠️ [오토 오디오] LoRA 누적 기록 실패: {record_exc}")
            get_logger().log(format_auto_audio_decision_log(decision, target_file))
        except Exception as exc:
            get_logger().log(f"  ⚠️ [오토 오디오] 자동 프리셋 실패: {exc}")

        self.video_processor.clear_fast_mode_overrides()
        get_logger().log("  🎯 정확도 우선: 오토 오디오 + STT 앙상블 + LLM 검수 적용")

        if hasattr(self.ui, '_sig_update_queue'):
            self.ui._sig_update_queue.emit(queue_index, "⏳ 오디오 추출 중", "", "", "")

        res = self._validate_audio_extract_result(
            self.video_processor.extract_audio(target_file),
            target_file,
        )
        if not res:
            get_logger().log(f"❌ 오디오 추출 실패: {vname}")
            if hasattr(self.ui, '_sig_update_queue'):
                self.ui._sig_update_queue.emit(queue_index, "❌ 추출 실패", "", "", "")
            return False

        self.video_processor.clear_fast_mode_overrides()

        chunk_dir, vad_segs = res
        if hasattr(self.ui, '_sig_set_vad_segments'):
            self.ui._sig_set_vad_segments.emit(vad_segs)

        # ── STEP 2: ETA 계산 + STT 시작 ──
        try:
            s = load_settings()
            model_key = "QUALITY:" + get_model_key(s)

            if target_file in getattr(self, '_video_durations', {}):
                video_duration_sec = self._video_durations[target_file]
            else:
                chunks = [f for f in os.listdir(chunk_dir) if f.endswith('.wav')]
                video_duration_sec = len(chunks) * 30.0

            expected_time = get_expected_time(model_key, video_duration_sec)
            self._expected_map = getattr(self, "_expected_map", {})
            self._expected_map[target_file] = float(expected_time) if expected_time and expected_time > 0 else -1.0

            if hasattr(self.ui, '_sig_update_queue'):
                eta_str = str(expected_time) if expected_time > 0 else "예상불가"
                self.ui._sig_update_queue.emit(queue_index, "🎯 자막 생성 중", eta_str, "", "")
            process_start_time = time.time()

        except Exception:
            process_start_time = time.time()
            video_duration_sec = 0.0

        # ── STEP 3: Whisper + LLM (동기 실행) ──
        import queue as _queue
        from core.engine.subtitle_engine import apply_final_gap_settings, optimize_segments
        from core.engine.subtitle_timing import align_stt_candidates_to_subtitle_segments

        _SENTINEL = object()
        opt_queue = _queue.Queue()
        all_segments = []

        def do_transcribe():
            try:
                for chunk_segs, c_idx, t_total in self.video_processor.transcribe(chunk_dir, is_fast_mode=False):
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

            get_logger().log("  🧠 정확도 우선: STT 결과를 LLM으로 교정/분리합니다.")

            seg_buffer = []
            last_t_total = 1

            def _flush():
                nonlocal seg_buffer
                if not seg_buffer:
                    return
                chunk_segs = seg_buffer
                seg_buffer = []
                try:
                    opt = optimize_segments(chunk_segs, vad_segments=vad_segs)
                except Exception as exc:
                    get_logger().log(f"  ⚠️ LLM 최적화 실패, STT 결과 유지: {exc}")
                    opt = chunk_segs

                for seg in opt:
                    if seg["start"] < 0.0:
                        seg["start"] = 0.0
                    if seg["end"] <= seg["start"]:
                        seg["end"] = seg["start"] + 0.5

                if hasattr(self, "_magnetize_by_saved_cut_boundaries"):
                    opt = self._magnetize_by_saved_cut_boundaries(
                        opt,
                        context="정확도 우선 정식 컷",
                        include_provisional=False,
                    )
                if hasattr(self, "_split_by_saved_cut_boundaries"):
                    opt = self._split_by_saved_cut_boundaries(opt, context="정확도 우선 최종 자막")
                opt = self._align_subtitle_segments_to_vad(opt, vad_segs, context="정확도 우선 배치")
                opt = apply_final_gap_settings(opt, force=True)
                if hasattr(self, "_magnetize_by_saved_cut_boundaries"):
                    opt = self._magnetize_by_saved_cut_boundaries(
                        opt,
                        context="정확도 우선 임시 컷",
                        include_confirmed=False,
                        include_provisional=True,
                    )
                if hasattr(self, "_split_by_saved_cut_boundaries"):
                    opt = self._split_by_saved_cut_boundaries(opt, context="정확도 우선 최종 자막")
                opt = align_stt_candidates_to_subtitle_segments(opt)
                all_segments.extend([dict(seg) for seg in opt])

                if hasattr(self.ui, "_sig_append_segments"):
                    self.ui._sig_append_segments.emit(opt)

            while self._active:
                item = opt_queue.get()
                if item is _SENTINEL:
                    _flush()
                    break

                chunk_segs, _c_idx, t_total = item
                last_t_total = t_total

                total_files = len(self.files_to_process)

                # 예상시간 기반 진행률
                total_exp = getattr(self, 'total_expected_time', 0.0)
                if total_exp > 0:
                    # 이전 파일들의 예상시간 합산
                    done_exp = 0.0
                    exp_map = getattr(self, '_expected_map', {})
                    for j in range(queue_index):
                        f = self.files_to_process[j]
                        done_exp += exp_map.get(f, 0.0) if exp_map.get(f, 0.0) > 0 else 0.0
                    # 현재 파일 진행분
                    cur_exp = exp_map.get(self.files_to_process[queue_index], 0.0)
                    if cur_exp > 0 and t_total > 0:
                        cur_progress = cur_exp * (c_idx / t_total)
                    else:
                        cur_progress = 0.0
                    pct = min(99, int(((done_exp + cur_progress) / total_exp) * 100))
                else:
                    pct = int(((queue_index + (c_idx / t_total if t_total > 0 else 0)) / total_files) * 100)


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

        t1 = threading.Thread(target=do_transcribe, daemon=True, name="quality-batch-transcriber")
        t2 = threading.Thread(target=do_optimize, daemon=True, name="quality-batch-optimizer")
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # ── 큐 즉시 업데이트 ──
        if hasattr(self.ui, '_sig_update_queue'):
            try:
                elapsed = time.time() - process_start_time
                exp = -1.0
                try:
                    exp = getattr(self, "_expected_map", {}).get(target_file, -1.0)
                except Exception:
                    exp = -1.0

                def _fmt(sec):
                    m, s = divmod(int(sec), 60)
                    return f"{m:02d}:{s:02d}"

                if exp and exp > 0:
                    eta_done = f"{_fmt(elapsed)} / {_fmt(exp)}"
                else:
                    eta_done = f"{_fmt(elapsed)} / -"

                if hasattr(self.ui, '_sig_update_queue'):
                    try:
                        self.ui._sig_update_queue.emit(queue_index, "✅ 자막 생성 완료", eta_done, "", "")
                    except RuntimeError:
                        pass

            except RuntimeError:
                pass

        # ── 큐 헤더 진행률 갱신 ──
        total_exp = getattr(self, 'total_expected_time', 0.0)
        if total_exp > 0 and hasattr(self.ui, '_sig_update_queue_header'):
            done_exp = 0.0
            exp_map = getattr(self, '_expected_map', {})
            for j in range(queue_index + 1):
                f = self.files_to_process[j]
                done_exp += exp_map.get(f, 0.0) if exp_map.get(f, 0.0) > 0 else 0.0
            pct = min(100, int((done_exp / total_exp) * 100))
            self.ui._sig_update_queue_header.emit(queue_index + 1, len(self.files_to_process), pct, "")             

        # ── 히스토리 기록 ──
        try:
            model_key = get_model_key()
            proc_time = time.time() - process_start_time
            add_history(model_key, video_duration_sec, proc_time)
        except Exception:
            pass

        # ── STEP 5~6: SRT 저장 + 내보내기 ──
        all_segments = apply_final_gap_settings(all_segments, force=True)
        all_segments = align_stt_candidates_to_subtitle_segments(all_segments)
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
                # B7 fix: explicit queue status after each file
                if ok and hasattr(self.ui, '_sig_update_queue'):
                    try:
                        self.ui._sig_update_queue.emit(i, "✅ 완료", "", "", "")
                    except RuntimeError:
                        pass
                elif not ok and hasattr(self.ui, '_sig_update_queue'):
                    try:
                        self.ui._sig_update_queue.emit(i, "❌ 오류", "", "", "")
                    except RuntimeError:
                        pass
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
            clear_runtime_settings_override()
            try:
                if hasattr(self.ui, "_clear_runtime_quality_override"):
                    self.ui._clear_runtime_quality_override()
            except Exception:
                pass
            try:
                if hasattr(self.ui, 'request_show_home'):
                    self.ui.request_show_home()
            except Exception:
                pass
