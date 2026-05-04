# Version: 03.14.34
# Phase: PHASE2
"""
core/pipeline/single_pipeline.py
SinglePipelineMixin — 단일 파일 / 배치 파이프라인 (_run_all, _process_one)
"""
import os
import threading
import traceback
import queue
import time

from core.runtime import config
from core.runtime.logger import get_logger
from core.settings import load_settings, get_model_key
from core.time_history import get_expected_time, add_history

_SENTINEL = object()


def _is_deleted_qt_error(exc: BaseException) -> bool:
    return "wrapped C/C++ object" in str(exc) and "has been deleted" in str(exc)


def _should_flush_final_subtitle_buffer(
    current_duration: float,
    chunk_time_limit: int,
    *,
    stt_ensemble_enabled: bool,
) -> bool:
    try:
        return float(current_duration or 0.0) > 0.0
    except Exception:
        return False


def _should_flush_live_subtitle_buffer(
    current_duration: float,
    chunk_time_limit: int,
    *,
    stt_ensemble_enabled: bool,
    individual_queue_mode: bool,
) -> bool:
    return _should_flush_final_subtitle_buffer(
        current_duration,
        chunk_time_limit,
        stt_ensemble_enabled=stt_ensemble_enabled,
    )


class SinglePipelineMixin:
    """단일 / 배치 품질모드 파이프라인."""

    def _append_live_segments_to_editor(self, segments: list[dict]) -> None:
        segments = [dict(seg) for seg in list(segments or []) if isinstance(seg, dict)]
        if not segments:
            return
        if (
            getattr(self, "_individual_queue_mode", False)
            and callable(self._ui_attr("append_segments_to_editor_and_wait"))
        ):
            for seg in segments:
                if not self._active or not self._ui_is_alive():
                    return
                self._ui_call("append_segments_to_editor_and_wait", [seg], timeout_sec=2.0)
                time.sleep(0.04)
            return
        self._ui_emit("_sig_append_segments", segments)

    def _ui_is_alive(self) -> bool:
        try:
            ui = getattr(self, "ui", None)
            if ui is None:
                return False
            try:
                from PyQt6 import sip
                if sip.isdeleted(ui):
                    return False
            except Exception:
                pass
            return True
        except RuntimeError:
            return False

    def _ui_attr(self, name: str, default=None):
        if not self._ui_is_alive():
            self._active = False
            return default
        try:
            return getattr(self.ui, name, default)
        except RuntimeError:
            self._active = False
            return default

    def _ui_object(self):
        if not self._ui_is_alive():
            self._active = False
            return None
        try:
            return self.ui
        except RuntimeError:
            self._active = False
            return None

    def _ui_emit(self, signal_name: str, *args) -> bool:
        signal = self._ui_attr(signal_name)
        if signal is None:
            return False
        try:
            signal.emit(*args)
            return True
        except RuntimeError:
            self._active = False
            return False

    def _ui_call(self, method_name: str, *args, **kwargs):
        method = self._ui_attr(method_name)
        if not callable(method):
            return False
        try:
            method(*args, **kwargs)
            return True
        except RuntimeError:
            self._active = False
            return False

    def _run_all(self):
        total_files = len(self.files_to_process)

        try:
            for i, target_file in enumerate(self.files_to_process):
                if not self._active:
                    return

                self._ui_emit("_sig_update_queue", i, "⏳ 오디오 추출 중", "", "", "")
                self._ui_emit("_sig_update_queue_header", i + 1, total_files, 0, "")

                self._process_one(target_file, i)

            self._ui_emit("_sig_update_queue_header", total_files, total_files, 100, "")

            if bool(self._ui_attr("_is_auto_pipeline", False)):
                self._send_ntfy_notification(
                    title=f"🏆 {config.APP_NAME} 작업 종료",
                    message=f"🎉 {total_files}개 파일 처리 완료!\n아이패드에서 확인해 보세요, 대표님.",
                    tags="checkered_flag,tada",
                )

        except Exception as e:
            if _is_deleted_qt_error(e):
                self._active = False
            elif str(e) not in ("USER_PREV", "USER_EXIT"):
                get_logger().log(f"\n❌ 치명적 에러: {e}")
                get_logger().log(traceback.format_exc())

        finally:
            self._active = False
            try:
                from core.settings import clear_runtime_settings_override

                clear_runtime_settings_override()
                ui = self._ui_object()
                if ui is not None and hasattr(ui, "_clear_runtime_quality_override"):
                    ui._clear_runtime_quality_override()
            except Exception:
                pass
            try:
                ui = self._ui_object()
                if ui is not None and hasattr(ui, "_auto_processing_active"):
                    ui._auto_processing_active = False
                self._ui_call("_tick_home_watchdog_labels")
            except Exception:
                pass

    def _process_one(self, target_file, queue_index):
        if getattr(self, "_individual_queue_mode", False):
            self._reset_backend_individual_clip_context(invalidate_prefetch=True)
            self._reset_ui_individual_clip_context(clear_project=True)

        # ── STEP 0: 백업 ──
        self._backup_existing(target_file)

        # ── 이벤트/콜백 ──
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
            start_event.set()
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

        # 변경: 첫 파일은 수동, 이후 파일은 자동 진행
        is_auto_mode = getattr(self, "is_auto_start", False) or (
            queue_index > 0 and len(self.files_to_process) > 1
        )

        open_editor_method = (
            "open_editor_for_file_and_wait"
            if callable(self._ui_attr("open_editor_for_file_and_wait"))
            else "open_editor_for_file"
        )
        if not self._ui_call(
            open_editor_method,
            target_file, on_save, on_start, on_prev, on_exit, is_batch=is_auto_mode
        ):
            raise Exception("USER_EXIT")

        if is_auto_mode and not getattr(self, "_individual_queue_mode", False):
            threading.Timer(0.05, on_start).start()

        start_event.wait()
        if action_state[0] == "prev":
            self._ui_call("request_show_home")
            raise Exception("USER_PREV")
        if action_state[0] == "exit":
            self._ui_call("request_show_home")
            raise Exception("USER_EXIT")
        if action_state[0] == "next":
            return
        if action_state[0] == "restart":
            self._handle_restart(target_file)
            action_state[0] = "start"

        if action_state[0] == "start":
            try:
                ui = self._ui_object()
                project_path = str(getattr(ui, "_current_project_path", "") or "") if ui is not None else ""
                media_files = list(getattr(ui, "_multiclip_files", []) or []) if ui is not None else []
                if not media_files:
                    media_files = [target_file]
                if not project_path and ui is not None and media_files:
                    from core.project.project_manager import create_project
                    from core.path_manager import get_srt_path

                    base_name = os.path.splitext(os.path.basename(media_files[0]))[0]
                    editor = getattr(ui, "_editor_widget", None)
                    editor_settings = dict(getattr(editor, "settings", {}) or {})
                    project_path = create_project(
                        name=base_name,
                        media_paths=media_files,
                        srt_path=get_srt_path(media_files[0]),
                        user_settings=editor_settings,
                    )
                    ui._current_project_path = project_path
                get_logger().log("  🎬 [컷 경계] 시작 전 분석 단계 확인 중...")
                self._auto_scan_cut_boundaries_for_start(project_path, media_files)
                self._ui_emit("_sig_refresh_cut_boundary_placeholder")
            except Exception as exc:
                get_logger().log(f"  ⚠️ [컷 경계] 시작 전 백그라운드 준비 실패: {exc}")

        # ── STT 파이프라인 루프 ──
        while True:
            self._active = True
            self._speaker_map = []
            edit_event.clear()
            if hasattr(self, "_apply_personalization_runtime_override_for_file"):
                self._apply_personalization_runtime_override_for_file(target_file)
            self._reload_speaker_settings()
            vname = os.path.basename(target_file)
            fsize = (
                os.path.getsize(target_file) / (1024 * 1024)
                if os.path.exists(target_file)
                else 0
            )

            get_logger().log(
                f"\n{'=' * 44}\n🎬 [{queue_index + 1}/{len(self.files_to_process)}] {vname}"
                f"\n{'=' * 44}\n\n{'─' * 44}\n  📂 파일: {vname} ({fsize:.1f} MB)\n{'─' * 44}"
            )

            # 정확도 우선 파이프라인: legacy batch override가 남아있으면 제거
            if hasattr(self, 'video_processor'):
                self.video_processor.clear_fast_mode_overrides()
                if getattr(self, "_individual_queue_mode", False):
                    self.video_processor.set_auto_audio_tune_overrides(None)
            if hasattr(self, "video_processor"):
                self.video_processor.stage_callback = (
                    lambda status, qi=queue_index: self._ui_emit("_sig_update_queue", qi, status, "", "", "")
                )
            try:
                # ✅ 순서 고정:
                # 컷 경계/주제없음 중분류가 먼저 확정된 뒤 STT1/STT2가 시작되어야 한다.
                if hasattr(self, "_wait_cut_boundary_prescan_before_stt"):
                    self._wait_cut_boundary_prescan_before_stt()

                cut_boundary_snapshot = (
                    self._cut_boundary_snapshot_for_pipeline()
                    if hasattr(self, "_cut_boundary_snapshot_for_pipeline")
                    else {"cut_boundaries": [], "provisional_cut_boundaries": []}
                )
                pipeline_cut_boundaries = [
                    dict(row) for row in list(cut_boundary_snapshot.get("cut_boundaries", []) or [])
                ]
                pipeline_provisional_cut_boundaries = [
                    dict(row) for row in list(cut_boundary_snapshot.get("provisional_cut_boundaries", []) or [])
                ]

                # ✅ 컷 경계는 STT 입력 청크의 절대 경계다.
                # media_processor가 오디오 청크를 만들기 전에 hard cut을 주입한다.
                try:
                    if hasattr(self, "video_processor"):
                        hard_cuts = []
                        for row in pipeline_cut_boundaries:
                            try:
                                if isinstance(row, dict):
                                    sec = float(row.get("timeline_sec", row.get("time", row.get("start", 0.0))) or 0.0)
                                else:
                                    sec = float(row)
                                if sec > 0.0:
                                    hard_cuts.append(round(sec, 3))
                            except Exception:
                                continue
                        self.video_processor.hard_cut_boundaries = sorted(set(hard_cuts))
                        if hard_cuts:
                            get_logger().log(f"  ✂️ [컷 경계] STT 청크 hard cut {len(hard_cuts)}개 적용")
                except Exception as exc:
                    get_logger().log(f"  ⚠️ [컷 경계] STT 청크 hard cut 주입 실패: {exc}")

                res = self._get_audio_extract_result(target_file)
            finally:
                if hasattr(self, "video_processor"):
                    self.video_processor.stage_callback = None

            try:
                prefetch_ahead = 0 if getattr(self, "_individual_queue_mode", False) else max(1, int(load_settings().get("prefetch_ahead", 3)))
            except Exception:
                prefetch_ahead = 0 if getattr(self, "_individual_queue_mode", False) else 3
            if prefetch_ahead > 0:
                for _pf in self.files_to_process[queue_index + 1: queue_index + 1 + prefetch_ahead]:
                    self._prefetch_audio_for_file(_pf)

            if not res:
                get_logger().log("❌ 오디오 추출 실패")
                self._ui_emit("_sig_update_queue", queue_index, "❌ 오류", "", "", "")

                if action_state[0] == "restart":
                    get_logger().log("\n🔄 재시작합니다...")
                    action_state[0] = "next"
                    continue

                return

            chunk_dir, vad_segs = res
            self._ui_emit("_sig_set_vad_segments", vad_segs)

            get_logger().log("\n  [STT] Whisper 인식 → [자막 LLM] 교정/분리 파이프라인 가동...")

            try:
                s = load_settings()
                model_key = "QUALITY:" + get_model_key(s)

                if target_file in getattr(self, "_video_durations", {}):
                    video_duration_sec = self._video_durations[target_file]
                else:
                    chunks = [f for f in os.listdir(chunk_dir) if f.endswith(".wav")]
                    video_duration_sec = len(chunks) * 30.0

                expected_time = get_expected_time(model_key, video_duration_sec)
                if expected_time > 0:
                    self._ui_emit(
                        "_sig_update_queue",
                        queue_index, "자막 생성 중", str(expected_time), "", "",
                    )
                else:
                    self._ui_emit(
                        "_sig_update_queue",
                        queue_index, "자막 생성 중", "예상불가 (학습 중)", "", "",
                    )
                process_start_time = time.time()
            except Exception:
                process_start_time = time.time()
                video_duration_sec = 0.0

            opt_queue = queue.Queue()
            base_name = os.path.splitext(os.path.basename(target_file))[0]

            # 교체 (m4a 안전 fallback)
            cleaned_wav = os.path.join(config.OUTPUT_DIR, f"{base_name}_cleaned.wav")
            raw_wav = os.path.join(config.OUTPUT_DIR, f"{base_name}.wav")
            if os.path.exists(cleaned_wav):
                audio_for_diarization = cleaned_wav
            elif os.path.exists(raw_wav):
                audio_for_diarization = raw_wav
            else:
                wav_in_chunks = sorted(
                    [
                        os.path.join(chunk_dir, f)
                        for f in os.listdir(chunk_dir)
                        if f.endswith(".wav")
                    ]
                )
                audio_for_diarization = (
                    wav_in_chunks[0] if wav_in_chunks else target_file
                )

            t_diarize = None
            if self.max_speakers > 1:
                t_diarize = threading.Thread(
                    target=self._prepare_speaker_map,
                    args=(audio_for_diarization,),
                    daemon=True,
                    name="diarizer",
                )
                t_diarize.start()

            auto_collected_segs = []
            preview_opt_queue = queue.Queue()
            preview_opt_sentinel = object()

            def _emit_processed_preview(chunk_segs, _label="STT"):
                from core.pipeline.stt_preview_optimizer import optimize_stt_preview_segments

                preview = optimize_stt_preview_segments(
                    chunk_segs,
                    source_label=str(_label or "STT"),
                    vad_segments=vad_segs,
                    cut_boundaries=pipeline_cut_boundaries,
                    provisional_cut_boundaries=pipeline_provisional_cut_boundaries,
                )
                if preview and self._active:
                    self._ui_emit("_sig_preview_stt_segments", preview)

            def _preview_stt_segments(chunk_segs, _label="STT"):
                if not chunk_segs or not self._active:
                    return
                preview_opt_queue.put(([dict(seg) for seg in chunk_segs or []], str(_label or "STT")))

            def do_preview_optimize():
                while self._active:
                    item = preview_opt_queue.get()
                    if item is preview_opt_sentinel:
                        break
                    try:
                        chunk_segs, label = item
                        _emit_processed_preview(chunk_segs, label)
                    except Exception as exc:
                        get_logger().log(f"  ⚠️ STT 후보 자막 후처리 오류: {exc}")

            def do_transcribe():
                try:
                    if hasattr(self, "video_processor"):
                        self.video_processor.stage_callback = (
                            lambda status, qi=queue_index: self._ui_emit("_sig_update_queue", qi, status, "", "", "")
                        )
                    for chunk_segs, c_idx, t_total in self.video_processor.transcribe(
                        chunk_dir,
                        is_fast_mode=False,
                        preview_callback=_preview_stt_segments,
                    ):
                        if not self._active:
                            break
                        opt_queue.put((chunk_segs, c_idx, t_total))
                finally:
                    if hasattr(self, "video_processor"):
                        self.video_processor.stage_callback = None
                    preview_opt_queue.put(preview_opt_sentinel)
                    opt_queue.put(_SENTINEL)

            def _do_optimize_impl():
                from core.engine.subtitle_engine import apply_final_gap_settings, optimize_segments
                from core.engine.subtitle_timing import align_stt_candidates_to_subtitle_segments

                total_files = len(self.files_to_process)

                if t_diarize and t_diarize.is_alive():
                    get_logger().log("\n⏳ [안내] 화자 분리 연산 대기 중...")
                    t_diarize.join()

                try:
                    s = load_settings()
                    model_name = s.get("selected_model", "기본")
                    try:
                        from core.llm.secure_keys import get_api_key
                        from core.llm.openai_provider import is_openai_model
                        if "Gemini" in model_name:
                            api_key = get_api_key("google") or s.get("google_api_key", "")
                        elif is_openai_model(model_name):
                            api_key = get_api_key("openai") or s.get("openai_api_key", "")
                        else:
                            api_key = ""
                    except Exception:
                        api_key = ""
                    user_prompt = s.get("custom_prompt", "")
                    chunk_time_limit = int(s.get("chunk_time_limit", 60))
                    stt_ensemble_enabled = bool(s.get("stt_ensemble_enabled", False))
                except Exception:
                    model_name = ""
                    api_key = ""
                    user_prompt = ""
                    chunk_time_limit = 60
                    stt_ensemble_enabled = False

                is_gemini = "Gemini" in model_name
                seg_buffer = []
                last_c_idx = 0
                last_t_total = 1

                if stt_ensemble_enabled:
                    get_logger().log(
                        "  ⏳ [STT 앙상블] STT1/STT2 후보는 즉시 표시하고 "
                        "최종 자막은 병합/LLM 분석 완료 후 반영합니다."
                    )

                def _flush_buffer():
                    nonlocal seg_buffer
                    if not seg_buffer:
                        return
                    chunk_segs = seg_buffer
                    seg_buffer = []

                    try:
                        def _llm_progress(payload):
                            self._ui_emit("_sig_set_llm_review_segment", dict(payload or {}))

                        self._ui_emit("_sig_update_queue", queue_index, "⏳ [STT+자막 LLM] 인식 결과 교정/분리 중", "", "", "")
                        if is_gemini and len(chunk_segs) > 1:
                            from core.engine.subtitle_engine import ask_gemini_to_split
                            from core.utils import load_subtitle_rules

                            chunk_start = chunk_segs[0]["start"]
                            chunk_end = chunk_segs[-1]["end"]
                            full_text = " ".join([seg["text"] for seg in chunk_segs])
                            rules = load_subtitle_rules()
                            _llm_progress(
                                {
                                    "active": True,
                                    "idx": 0,
                                    "total": 1,
                                    "start": chunk_start,
                                    "end": chunk_end,
                                    "text": full_text,
                                    "line": int(chunk_segs[0].get("line", -1) or -1),
                                }
                            )
                            res_chunks = ask_gemini_to_split(
                                full_text, 15, rules, model_name, user_prompt, api_key
                            )
                            if res_chunks and len(res_chunks) > 0:
                                opt = []
                                dur = (chunk_end - chunk_start) / len(res_chunks)
                                for i, txt in enumerate(res_chunks):
                                    opt.append(
                                        {
                                            "start": round(chunk_start + i * dur, 3),
                                            "end": round(
                                                chunk_start + (i + 1) * dur, 3
                                            ),
                                            "text": txt,
                                        }
                                    )
                            else:
                                opt = optimize_segments(chunk_segs, vad_segments=vad_segs, llm_progress_callback=_llm_progress)
                        else:
                            opt = optimize_segments(chunk_segs, vad_segments=vad_segs, llm_progress_callback=_llm_progress)
                    except Exception as e:
                        get_logger().log(f"  ❌ 최적화 오류: {e}")
                        opt = chunk_segs
                    finally:
                        self._ui_emit("_sig_set_llm_review_segment", {"active": False})

                    if not self._active or not self._ui_is_alive():
                        return

                    for seg in opt:
                        if seg["start"] < 0.0:
                            seg["start"] = 0.0
                        if seg["end"] <= seg["start"]:
                            seg["end"] = seg["start"] + 0.5

                    opt = self._magnetize_by_saved_cut_boundaries(
                        opt,
                        context="에디터 최종 자막 정식 컷",
                        include_provisional=False,
                    )
                    opt = self._split_by_saved_cut_boundaries(opt, context="에디터 최종 자막")
                    opt = self._align_subtitle_segments_to_vad(opt, vad_segs, context="에디터")

                    if self.max_speakers > 1 and self._speaker_map:
                        from core.audio.diarize import get_speaker_for_segment

                        for seg in opt:
                            spk_full = get_speaker_for_segment(
                                seg["start"], seg["end"], self._speaker_map
                            )
                            seg["speaker"] = spk_full.replace("SPEAKER_", "")

                        grouped_opt = []
                        for seg in opt:
                            text = seg.get("text", "").strip()
                            if text.startswith("-"):
                                text = text.lstrip("-").strip()
                            spk = seg.get("speaker", "00")
                            if not grouped_opt:
                                seg["text_list"] = [text]
                                seg["speaker_list"] = [spk]
                                grouped_opt.append(seg)
                            else:
                                prev = grouped_opt[-1]
                                gap = seg["start"] - prev["end"]
                                if (
                                    gap < 1.5
                                    and spk != prev["speaker_list"][-1]
                                    and len(prev["speaker_list"]) < 2
                                ):
                                    prev["text_list"].append(text)
                                    prev["speaker_list"].append(spk)
                                    prev["end"] = max(prev["end"], seg["end"])
                                else:
                                    seg["text_list"] = [text]
                                    seg["speaker_list"] = [spk]
                                    grouped_opt.append(seg)

                        for seg in grouped_opt:
                            if len(seg.get("text_list", [])) > 1:
                                seg["text"] = (
                                    f"- {seg['text_list'][0]}\n- {seg['text_list'][1]}"
                                )
                            else:
                                seg["text"] = (
                                    seg["text_list"][0]
                                    if "text_list" in seg
                                    else seg.get("text", "")
                                )
                            if "text_list" in seg:
                                del seg["text_list"]
                        opt = grouped_opt

                    opt = apply_final_gap_settings(opt, force=True)
                    opt = self._magnetize_by_saved_cut_boundaries(
                        opt,
                        context="에디터 최종 자막 임시 컷",
                        include_confirmed=False,
                        include_provisional=True,
                    )
                    opt = self._split_by_saved_cut_boundaries(opt, context="에디터 최종 자막")
                    opt = align_stt_candidates_to_subtitle_segments(opt)
                    auto_collected_segs.extend([dict(seg) for seg in opt])

                    if not self._active or not self._ui_is_alive():
                        return

                    try:
                        self._append_live_segments_to_editor(opt)
                        self._ui_emit("_sig_update_status", last_c_idx, last_t_total)
                    except Exception:
                        pass

                while self._active:
                    item = opt_queue.get()
                    if not self._ui_is_alive():
                        self._active = False
                        break
                    if item is _SENTINEL:
                        _flush_buffer()
                        break

                    chunk_segs, c_idx, t_total = item
                    last_c_idx = c_idx
                    last_t_total = t_total

                    if t_total > 0:
                        overall_pct = int(
                            ((queue_index + (c_idx / t_total)) / total_files) * 100
                        )
                    else:
                        overall_pct = int((queue_index / total_files) * 100)

                    self._ui_emit("_sig_update_status", c_idx, t_total)

                    try:
                        self._ui_emit(
                            "_sig_update_queue_header",
                            queue_index + 1, total_files, overall_pct, "",
                        )
                    except Exception:
                        pass

                    if not chunk_segs:
                        try:
                            self._ui_emit("_sig_update_status", c_idx, t_total)
                        except Exception:
                            pass
                        continue

                    seg_buffer.extend(chunk_segs)
                    buffer_start = seg_buffer[0]["start"]
                    buffer_end = seg_buffer[-1]["end"]
                    current_duration = buffer_end - buffer_start

                    if _should_flush_live_subtitle_buffer(
                        current_duration,
                        chunk_time_limit,
                        stt_ensemble_enabled=stt_ensemble_enabled,
                        individual_queue_mode=bool(getattr(self, "_individual_queue_mode", False)),
                    ):
                        _flush_buffer()

                self._ui_emit("_sig_update_status", last_t_total, last_t_total)

            def do_optimize():
                try:
                    _do_optimize_impl()
                except Exception as e:
                    if _is_deleted_qt_error(e):
                        self._active = False
                        return
                    get_logger().log(
                        "  ❌ optimizer 스레드 오류: "
                        f"{e}\n{traceback.format_exc()}"
                    )

            t_trans = threading.Thread(
                target=do_transcribe, daemon=True, name="transcriber"
            )
            t_opt = threading.Thread(target=do_optimize, daemon=True, name="optimizer")
            t_preview = threading.Thread(target=do_preview_optimize, daemon=True, name="stt-preview-optimizer")
            t_preview.start()
            t_trans.start()
            t_opt.start()
            t_trans.join()
            t_preview.join()
            t_opt.join()

            # ✅ STT 완료 → 큐 즉시 업데이트
            if not self._active:
                return

            self._ui_emit("_sig_update_queue", queue_index, "저장 준비 중", "", "", "")

            try:
                s = load_settings()
                model_key = "QUALITY:" + get_model_key(s)
                proc_time = time.time() - process_start_time
                add_history(model_key, video_duration_sec, proc_time)
            except Exception:
                pass

            if is_auto_mode:
                from core.engine.subtitle_engine import apply_final_gap_settings
                from core.engine.subtitle_timing import align_stt_candidates_to_subtitle_segments

                nonlocal_final = apply_final_gap_settings(auto_collected_segs[:], force=True)
                nonlocal_final = self._magnetize_by_saved_cut_boundaries(
                    nonlocal_final,
                    context="자동모드 최종 자막 임시 컷",
                    include_confirmed=False,
                    include_provisional=True,
                )
                nonlocal_final = self._split_by_saved_cut_boundaries(nonlocal_final, context="자동모드 최종 자막")
                nonlocal_final = align_stt_candidates_to_subtitle_segments(nonlocal_final)

                def _auto_proceed():
                    nonlocal final_segments
                    final_segments = nonlocal_final
                    action_state[0] = "next"
                    edit_event.set()

                auto_delay = 0.35 if getattr(self, "_individual_queue_mode", False) else 0.05
                threading.Timer(auto_delay, _auto_proceed).start()

            edit_event.wait()

            if action_state[0] == "restart":
                self._handle_restart(target_file)
                action_state[0] = "next"
                continue

            if not self._active:
                return
            if action_state[0] == "prev":
                self._ui_call("request_show_home")
                raise Exception("USER_PREV")
            if action_state[0] == "exit":
                self._ui_call("request_show_home")
                raise Exception("USER_EXIT")

            # ── STEP 5~6: 저장 + 내보내기 ──
            if not self._ui_is_alive():
                self._active = False
                return
            self._save_and_export(target_file, queue_index, final_segments, is_auto_mode)

            if action_state[0] == "restart":
                self._handle_restart(target_file)
                action_state[0] = "start"
                continue
            break

        if action_state[0] == "exit" or not getattr(self, "_active", True):
            try:
                if self._ui_is_alive():
                    self._ui_call("request_show_home")
            except Exception:
                pass
            raise Exception("USER_EXIT")
