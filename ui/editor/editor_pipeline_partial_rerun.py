# Version: 01.00.00
# Phase: PHASE2
from __future__ import annotations

import os
import queue
import threading

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from core.runtime import config
from core.runtime.logger import get_logger
from ui.project.project_session_runtime import set_project_boundary_rows


class PartialSignals(QObject):
    status = pyqtSignal(str, str)
    progress = pyqtSignal(int, int)
    chunk_time = pyqtSignal(float)
    done = pyqtSignal(list)
    finished = pyqtSignal()


class EditorPipelinePartialRerunMixin:
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
        if main_w is not None:
            set_project_boundary_rows(main_w, list(prefix_time_rows), emit_boundary_signal=True)

        set_project_boundary_rows(self, list(prefix_time_rows), emit_boundary_signal=False)
        try:
            if hasattr(self, "_set_auto_cut_boundary_scan_lines"):
                self._set_auto_cut_boundary_scan_lines(list(prefix_provisionals))
        except Exception:
            pass
        try:
            timeline = getattr(self, "timeline", None)
            if timeline is not None:
                if hasattr(timeline, "set_boundary_times"):
                    timeline.set_boundary_times(list(prefix_time_rows))
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
        if hasattr(self, "timeline") and hasattr(self.timeline, "canvas"):
            self.timeline.canvas.re_recog_progress = sec
            self.timeline.canvas.update()

    def _run_partial_backend(self, start_sec, end_sec, is_single=False):
        main_w = self.window()
        if not (main_w and main_w.backend):
            return
        if is_single:
            self.sm.start_partial_segment()
        else:
            self.sm.start_partial_from_here()
        rerun_cut_boundaries = not bool(is_single)
        prefix_vad = self._prepare_partial_rerun_state(
            start_sec,
            end_sec,
            rerun_cut_boundaries=rerun_cut_boundaries,
        )
        if hasattr(self, "timeline") and hasattr(self.timeline, "canvas"):
            self.timeline.canvas.re_recog_zone = (start_sec, end_sec)
            self.timeline.canvas.re_recog_progress = start_sec
            self.timeline.canvas.update()
        self._partial_signals = PartialSignals()
        self._partial_signals.status.connect(lambda _code, msg: self.update_status(msg))
        self._partial_signals.progress.connect(self.update_progress)
        self._partial_signals.chunk_time.connect(self._update_partial_progress)
        if hasattr(self, "insert_partial_segments"):
            self._partial_signals.done.connect(self.insert_partial_segments)

        def on_finished():
            self.sm.complete_ai()
            self._clear_processing_indicators()
            if hasattr(self, "timeline") and hasattr(self.timeline, "canvas"):
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
                    from core.frame_time import frame_to_sec, sec_to_frame

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
