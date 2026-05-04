# Version: 03.14.34
# Phase: PHASE2
"""
core/pipeline/multiclip_pipeline.py
MulticlipPipelineMixin — 멀티클립 품질모드 파이프라인 (start_multiclip_pipeline, _run_multiclip)
"""
import os
import queue
import threading
import traceback
import time

from core.runtime.logger import get_logger
from core.settings import load_settings, get_model_key
from core.time_history import get_expected_time
from core.media_info import probe_media_many


class MulticlipPipelineMixin:
    """멀티클립 품질모드: 클립 단위 STT/LLM 파이프라인 → 하나의 에디터에서 편집."""

    def _move_existing_multiclip_srts_to_backup(self, files):
        """기존자막 reuse 거부 시 개별 SRT를 자막백업 폴더로 이동합니다."""
        import datetime
        import shutil
        from core.path_manager import get_srt_path

        moved = 0
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        for target_file in files:
            srt_path = get_srt_path(target_file)
            if not srt_path or not os.path.exists(srt_path):
                continue
            base_name = os.path.basename(srt_path)
            if base_name.endswith("_통합.srt"):
                continue
            backup_dir = os.path.join(os.path.dirname(srt_path), "자막백업")
            os.makedirs(backup_dir, exist_ok=True)
            dst = os.path.join(backup_dir, f"{base_name}.{timestamp}.bak")
            try:
                shutil.move(srt_path, dst)
                moved += 1
                get_logger().log(f"📦 기존 자막 백업 이동: {base_name} → 자막백업")
            except Exception as e:
                get_logger().log(f"⚠️ 기존 자막 백업 이동 실패: {base_name} / {e}")
        if moved:
            get_logger().log(f"✅ 기존 자막 {moved}개를 자막백업 폴더로 이동했습니다.")

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
        self._reuse_clip_indices = set()

        try:
            from ui.dialogs.message_box import ask_yes_no
            candidates = []
            for _f in self.files_to_process:
                if os.path.exists(os.path.splitext(_f)[0] + '.srt'):
                    candidates.append(_f)
            if getattr(self, '_force_no_reuse_once', False):
                self._force_no_reuse_once = False
                self._reuse_existing_multiclip_subtitles = False
                if candidates:
                    self._move_existing_multiclip_srts_to_backup(candidates)
            elif candidates:
                self._reuse_existing_multiclip_subtitles = ask_yes_no(
                    self.ui,
                    "기존 자막 사용",
                    "기존 자막을 사용하시겠습니까?",
                )
                if not self._reuse_existing_multiclip_subtitles:
                    self._move_existing_multiclip_srts_to_backup(candidates)
        except Exception:
            self._reuse_existing_multiclip_subtitles = False
        # reuse flag를 ui(main_window)에도 동기화
        try:
            self.ui._reuse_existing_multiclip_subtitles = self._reuse_existing_multiclip_subtitles
        except Exception:
            pass

        with self._prefetch_lock:
            self._prefetch_generation += 1
            self._prefetch_cache = {}
            self._prefetch_threads = {}

        if not self.files_to_process:
            return
        if hasattr(self.ui, "init_queue_list"):
            self.ui.init_queue_list(self.files_to_process)

        get_logger().log(
            f"🎬 멀티클립 품질모드: {len(self.files_to_process)}개 클립 STT/LLM 병렬 파이프라인"
        )
        self._pipeline_thread = threading.Thread(
            target=self._run_multiclip, daemon=True, name="multiclip-main"
        )
        self._pipeline_thread.start()

    def _emit_multiclip_queue_status(self, idx, status, expected="", info_txt="", len_txt=""):
        if hasattr(self.ui, "_sig_update_queue"):
            self.ui._sig_update_queue.emit(idx, status, expected, info_txt, len_txt)

    def _offset_multiclip_segments(self, segments, offset, clip_idx, clip_file=None):
        for seg in segments:
            seg["start"] = float(seg.get("start", 0.0)) + offset
            seg["end"] = float(seg.get("end", 0.0)) + offset
            seg["_clip_idx"] = clip_idx
            if clip_file:
                seg["_clip_file"] = clip_file
            if "speaker" not in seg:
                seg["speaker"] = seg.get("spk_id", "00")
            for word in seg.get("words", []) or []:
                word["start"] = float(word.get("start", 0.0)) + offset
                word["end"] = float(word.get("end", 0.0)) + offset
            for candidate in seg.get("stt_candidates", []) or []:
                if not isinstance(candidate, dict):
                    continue
                if candidate.get("start") is not None:
                    candidate["start"] = float(candidate.get("start", 0.0)) + offset
                if candidate.get("end") is not None:
                    candidate["end"] = float(candidate.get("end", 0.0)) + offset
                for word in candidate.get("words", []) or []:
                    if not isinstance(word, dict):
                        continue
                    if word.get("start") is not None:
                        word["start"] = float(word.get("start", 0.0)) + offset
                    if word.get("end") is not None:
                        word["end"] = float(word.get("end", 0.0)) + offset
            asr_meta = seg.get("asr_metadata")
            if isinstance(asr_meta, dict):
                asr_meta["_clip_idx"] = clip_idx
                for word in asr_meta.get("words") or []:
                    if not isinstance(word, dict):
                        continue
                    if word.get("start") is not None:
                        word["start"] = float(word.get("start", 0.0)) + offset
                    if word.get("end") is not None:
                        word["end"] = float(word.get("end", 0.0)) + offset
        return segments

    def _sanitize_multiclip_segments(self, segments, clip_idx, clip_file=None):
        clean = []
        for seg in segments or []:
            try:
                start = max(0.0, float(seg.get("start", 0.0)))
                end = float(seg.get("end", start + 0.5))
            except Exception:
                continue
            if end <= start:
                end = start + 0.5
            seg["start"] = start
            seg["end"] = end
            seg["_clip_idx"] = clip_idx
            if clip_file:
                seg["_clip_file"] = clip_file
            asr_meta = seg.get("asr_metadata")
            if isinstance(asr_meta, dict):
                asr_meta["_clip_idx"] = clip_idx
            if "speaker" not in seg:
                seg["speaker"] = seg.get("spk_id", "00")
            clean.append(seg)
        return clean

    def _try_load_existing_multiclip_srt(self, target_file, clip_idx, offset):
        if not getattr(self, "_reuse_existing_multiclip_subtitles", False):
            return None

        existing_srt = os.path.splitext(target_file)[0] + ".srt"
        vname = os.path.basename(target_file)
        if not os.path.exists(existing_srt):
            return None

        try:
            from core.srt_parser import parse_srt
            segments = parse_srt(existing_srt)
        except Exception as e:
            get_logger().log(f"  ⚠️ 기존 자막 로드 실패: {vname} / {e}")
            return None

        if not segments:
            get_logger().log(f"  ⚠️ 기존 자막 파일이 비어있음: {vname}")
            return None

        self._offset_multiclip_segments(segments, offset, clip_idx, target_file)
        self._reuse_clip_indices.add(clip_idx)
        try:
            self.ui._reuse_clip_indices = set(self._reuse_clip_indices)
        except Exception:
            pass
        return segments

    def _run_multiclip_stt_llm_pipeline(self, clip_boundaries, total_files):
        """Whisper worker와 LLM worker를 분리해 클립 단위로 겹쳐 처리합니다."""
        from core.engine.subtitle_engine import apply_final_gap_settings, optimize_segments
        from core.engine.subtitle_timing import align_stt_candidates_to_subtitle_segments

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
        try:
            runtime_settings = load_settings()
        except Exception:
            runtime_settings = {}
        cut_boundary_enabled_runtime = bool(
            runtime_settings.get("cut_boundary_detection_enabled", runtime_settings.get("scan_cut_enabled", True))
        )

        stt_queue = queue.Queue()
        out_queue = queue.Queue()
        sentinel = object()
        preview_queue = queue.Queue()
        preview_sentinel = object()

        def preview_worker():
            from core.pipeline.stt_preview_optimizer import optimize_stt_preview_segments

            while self._active:
                item = preview_queue.get()
                if item is preview_sentinel:
                    break
                try:
                    offset = float(item.get("offset", 0.0) or 0.0)
                    local_cuts = []
                    for cut in pipeline_cut_boundaries:
                        row = dict(cut)
                        sec = float(row.get("timeline_sec", row.get("time", 0.0)) or 0.0) - offset
                        if sec > 0.0:
                            row["timeline_sec"] = sec
                            row["time"] = sec
                            local_cuts.append(row)
                    preview = optimize_stt_preview_segments(
                        item.get("segments") or [],
                        source_label=item.get("label") or "STT",
                        vad_segments=item.get("vad_segments") or [],
                        cut_boundaries=local_cuts,
                        provisional_cut_boundaries=pipeline_provisional_cut_boundaries,
                        cut_boundary_enabled=cut_boundary_enabled_runtime,
                        clip_offset=offset,
                        clip_idx=item.get("clip_idx"),
                        clip_path=item.get("clip_path"),
                    )
                    if preview and hasattr(self.ui, "_sig_preview_stt_segments"):
                        self.ui._sig_preview_stt_segments.emit(preview)
                except Exception as exc:
                    get_logger().log(f"  ⚠️ 멀티클립 STT 후보 자막 후처리 오류: {exc}")

        def stt_worker():
            try:
                get_logger().log("\n🎤 멀티클립 STT/LLM 병렬 파이프라인 시작...")

                try:
                    prefetch_ahead = max(1, int(runtime_settings.get("prefetch_ahead", 3)))
                except Exception:
                    prefetch_ahead = 3

                for i, target_file in enumerate(self.files_to_process):
                    if not self._active:
                        break

                    vname = os.path.basename(target_file)
                    bd = clip_boundaries[i]
                    offset = bd["start"]

                    get_logger().log(
                        f"\n{'=' * 44}\n🎬 [{i + 1}/{total_files}] {vname}\n{'=' * 44}"
                    )

                    existing = self._try_load_existing_multiclip_srt(target_file, i, offset)
                    if existing is not None:
                        self._emit_multiclip_queue_status(i, "⏳ LLM 대기", "", "", "")
                        get_logger().log(
                            f"  ✅ 기존 자막 사용: {vname} ({len(existing)}개 세그먼트)"
                        )
                        stt_queue.put(
                            {
                                "idx": i,
                                "name": vname,
                                "file": target_file,
                                "segments": existing,
                                "skip_optimize": True,
                            }
                        )
                        continue

                    self._emit_multiclip_queue_status(i, "⏳ 오디오 추출 중", "", "", "")
                    self._backup_existing(target_file)

                    if hasattr(self, 'video_processor'):
                        self.video_processor.clear_fast_mode_overrides()

                    # ✅ 순서 고정:
                    # 전체 컷 경계/주제없음 중분류가 먼저 확정된 뒤 클립별 STT가 시작되어야 한다.
                    if hasattr(self, "_wait_cut_boundary_prescan_before_stt"):
                        self._wait_cut_boundary_prescan_before_stt()

                    # ✅ 멀티클립: timeline 컷 경계를 현재 클립 local 초로 변환해 주입한다.
                    try:
                        if hasattr(self, "video_processor"):
                            local_hard_cuts = []
                            clip_start = float(offset or 0.0)
                            clip_end = float(bd.get("end", clip_start) or clip_start)
                            for row in pipeline_cut_boundaries:
                                try:
                                    if isinstance(row, dict):
                                        sec = float(row.get("timeline_sec", row.get("time", row.get("start", 0.0))) or 0.0)
                                    else:
                                        sec = float(row)
                                    if clip_start < sec < clip_end:
                                        local_hard_cuts.append(round(sec - clip_start, 3))
                                except Exception:
                                    continue
                            self.video_processor.hard_cut_boundaries = sorted(set(local_hard_cuts))
                            if local_hard_cuts:
                                get_logger().log(
                                    f"  ✂️ [컷 경계] 멀티클립 {i + 1} STT 청크 hard cut "
                                    f"{len(local_hard_cuts)}개 적용"
                                )
                    except Exception as exc:
                        get_logger().log(f"  ⚠️ [컷 경계] 멀티클립 STT 청크 hard cut 주입 실패: {exc}")

                    res = self._get_audio_extract_result(target_file)
                    for prefetch_file in self.files_to_process[i + 1: i + 1 + prefetch_ahead]:
                        self._prefetch_audio_for_file(prefetch_file)

                    if not res:
                        get_logger().log(f"  ❌ 오디오 추출 실패: {vname}")
                        self._emit_multiclip_queue_status(i, "❌ 오류", "", "", "")
                        stt_queue.put(
                            {
                                "idx": i,
                                "name": vname,
                                "file": target_file,
                                "segments": [],
                                "skip_optimize": True,
                            }
                        )
                        continue

                    chunk_dir, vad_segs = res
                    timeline_vad_segs = []
                    for vad in vad_segs or []:
                        try:
                            row = dict(vad)
                            local_start = float(row.get("start", 0.0) or 0.0)
                            local_end = float(row.get("end", local_start) or local_start)
                            row["start"] = local_start + offset
                            row["end"] = local_end + offset
                            timeline_vad_segs.append(row)
                        except Exception:
                            continue

                    if hasattr(self.ui, "_current_file_idx"):
                        self.ui._current_file_idx = i + 1
                    if hasattr(self.ui, "_sig_set_vad_segments"):
                        self.ui._sig_set_vad_segments.emit(vad_segs)
                    if hasattr(self.ui, "_sig_set_recog_zone"):
                        self.ui._sig_set_recog_zone.emit(offset, bd["end"])

                    self._emit_multiclip_queue_status(i, "⏳ Whisper 중", "", "", "")
                    get_logger().log("  🎤 Whisper 변환 중...")

                    clip_segments = []
                    def _preview_stt_segments(
                        chunk_segs,
                        _label="STT",
                        clip_offset=offset,
                        clip_idx=i,
                        clip_path=target_file,
                        local_vad_segments=vad_segs,
                    ):
                        if not chunk_segs or not self._active:
                            return
                        preview_queue.put(
                            {
                                "segments": [dict(seg) for seg in chunk_segs or []],
                                "label": str(_label or "STT"),
                                "offset": clip_offset,
                                "clip_idx": clip_idx,
                                "clip_path": clip_path,
                                "vad_segments": list(local_vad_segments or []),
                            }
                        )

                    for chunk_segs, _chunk_idx, _chunk_total in self.video_processor.transcribe(
                        chunk_dir,
                        preview_callback=_preview_stt_segments,
                    ):
                        if not self._active:
                            break
                        clip_segments.extend(chunk_segs)
                        if chunk_segs and hasattr(self.ui, "_sig_set_recog_progress"):
                            last_end = max(seg["end"] for seg in chunk_segs) + offset
                            self.ui._sig_set_recog_progress.emit(last_end)

                    if not self._active:
                        break

                    self._offset_multiclip_segments(clip_segments, offset, i, target_file)
                    get_logger().log(
                        f"    📊 Whisper 완료: {len(clip_segments)}개 세그먼트 → LLM 큐 전달"
                    )
                    self._emit_multiclip_queue_status(i, "⏳ LLM 대기", "", "", "")
                    stt_queue.put(
                        {
                            "idx": i,
                            "name": vname,
                            "file": target_file,
                            "segments": clip_segments,
                            "vad_segments": timeline_vad_segs,
                            "skip_optimize": False,
                        }
                    )
            except Exception as e:
                out_queue.put({"fatal": True, "error": e})
            finally:
                stt_queue.put(sentinel)
                preview_queue.put(preview_sentinel)
                if hasattr(self.ui, "_sig_set_recog_zone"):
                    self.ui._sig_set_recog_zone.emit(-1.0, -1.0)

        def llm_worker():
            while True:
                item = stt_queue.get()
                if item is sentinel:
                    break
                if not self._active:
                    break

                idx = item["idx"]
                vname = item["name"]
                clip_file = item.get("file")
                segments = item["segments"]

                if item.get("skip_optimize"):
                    optimized = self._sanitize_multiclip_segments(segments, idx, clip_file)
                else:
                    self._emit_multiclip_queue_status(idx, "⏳ LLM 최적화 중", "", "", "")
                    get_logger().log(
                        f"  🧠 LLM 최적화 중: [{idx + 1}/{total_files}] {vname}"
                    )
                    try:
                        optimized = optimize_segments(segments, vad_segments=item.get("vad_segments") or [])
                    except Exception as e:
                        get_logger().log(
                            f"  ⚠️ LLM 최적화 실패, Whisper 결과 유지: {vname} / {e}"
                        )
                        optimized = segments
                    optimized = self._sanitize_multiclip_segments(optimized, idx, clip_file)
                    optimized = self._magnetize_by_saved_cut_boundaries(
                        optimized,
                        context=f"멀티클립 {idx + 1} 최종 자막 정식 컷",
                        include_provisional=False,
                    )
                    optimized = self._split_by_saved_cut_boundaries(
                        optimized,
                        context=f"멀티클립 {idx + 1} 최종 자막",
                    )
                    optimized = self._align_subtitle_segments_to_vad(
                        optimized,
                        item.get("vad_segments") or [],
                        context=f"멀티클립 {idx + 1}",
                    )
                    optimized = apply_final_gap_settings(optimized, force=True)
                    optimized = self._magnetize_by_saved_cut_boundaries(
                        optimized,
                        context=f"멀티클립 {idx + 1} 최종 자막 임시 컷",
                        include_confirmed=False,
                        include_provisional=True,
                    )
                    optimized = self._split_by_saved_cut_boundaries(
                        optimized,
                        context=f"멀티클립 {idx + 1} 최종 자막",
                    )
                    optimized = align_stt_candidates_to_subtitle_segments(optimized)
                if item.get("skip_optimize"):
                    optimized = self._split_by_saved_cut_boundaries(
                        optimized,
                        context=f"멀티클립 {idx + 1} 기존 자막",
                    )
                    optimized = align_stt_candidates_to_subtitle_segments(optimized)

                out_queue.put(
                    {
                        "idx": idx,
                        "name": vname,
                        "file": clip_file,
                        "segments": optimized,
                        "skip_optimize": item.get("skip_optimize", False),
                    }
                )

            out_queue.put(sentinel)

        stt_thread = threading.Thread(
            target=stt_worker, daemon=True, name="multiclip-stt-worker"
        )
        llm_thread = threading.Thread(
            target=llm_worker, daemon=True, name="multiclip-llm-worker"
        )
        preview_thread = threading.Thread(
            target=preview_worker, daemon=True, name="multiclip-stt-preview-optimizer"
        )
        preview_thread.start()
        stt_thread.start()
        llm_thread.start()

        processed_count = 0
        next_emit_idx = 0
        pending_outputs = {}

        def _emit_ready_outputs():
            nonlocal next_emit_idx, processed_count
            while next_emit_idx in pending_outputs:
                ready = pending_outputs.pop(next_emit_idx)
                idx = ready["idx"]
                optimized = ready["segments"]
                if hasattr(self.ui, "_sig_append_segments"):
                    self.ui._sig_append_segments.emit(optimized)
                self._emit_multiclip_queue_status(
                    idx,
                    "기존자막" if ready.get("skip_optimize") else "완료",
                    "",
                    "",
                    "",
                )
                processed_count += 1
                get_logger().log(
                    f"  ✅ 클립 {idx + 1} 자막 완료 ({len(optimized)}개 세그먼트)"
                )
                next_emit_idx += 1

        while True:
            item = out_queue.get()
            if item is sentinel:
                _emit_ready_outputs()
                break
            if item.get("fatal"):
                raise item["error"]

            pending_outputs[int(item["idx"])] = item
            _emit_ready_outputs()

        stt_thread.join(timeout=2.0)
        llm_thread.join(timeout=2.0)
        preview_thread.join(timeout=2.0)
        return processed_count

    def _run_multiclip(self):
        restart_handoff = False
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

            media_infos = probe_media_many(self.files_to_process)
            for i, target_file in enumerate(self.files_to_process):
                vname = os.path.basename(target_file)
                try:
                    info = media_infos[i] if i < len(media_infos) else {}
                    clip_dur = info["duration"]
                    info_txt = info["info_txt"]
                    len_txt = info["len_txt"]

                    expected = get_expected_time(model_key, clip_dur)
                    if expected > 0:
                        total_expected += expected

                    if hasattr(self.ui, "_sig_update_queue"):
                        self.ui._sig_update_queue.emit(
                            i, "대기 중", str(expected), info_txt, len_txt
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

            # 시작 버튼 대기: 편집 중 마우스/키보드 조작이나 프리뷰 확인만으로 홈으로
            # 이동하지 않도록 시작 전 대기는 시간 제한을 두지 않는다.
            start_event.wait()

            if action_state[0] in ("prev", "exit"):
                self.ui.request_show_home()
                return

            # ── STEP 2: 클립별 Whisper + LLM 파이프라인 병렬 처리 ──
            processed_count = self._run_multiclip_stt_llm_pipeline(
                clip_boundaries, total_files
            )

            get_logger().log(
                f"\n🎊 전체 {processed_count}/{total_files}개 클립 처리 완료! 에디터에서 편집 후 저장하세요."
            )

            if hasattr(self.ui, "_sig_update_status"):
                self.ui._sig_update_status.emit(total_files, total_files)

            # 완료 상태 설정 → 버튼 "재시작"으로 전환 + 큐헤더 100%
            try:
                if hasattr(self.ui, "_sig_update_queue_header"):
                    self.ui._sig_update_queue_header.emit(total_files, total_files, 100, "")
            except Exception:
                pass
            try:
                if hasattr(self.ui, "_editor_widget") and self.ui._editor_widget:
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(0, self.ui._editor_widget._set_process_completed)
            except Exception:
                pass

            # ── 편집 대기 (재시작 루프) ──
            while True:
                edit_event.clear()
                edit_event.wait()

                if action_state[0] == "exit" or not self._active:
                    self.ui.request_show_home()
                    return

                if action_state[0] == "start":
                    # 재시작: 기존 자막 클리어 후 새 멀티클립 스레드로 STT 재실행
                    get_logger().log("\n🔄 멀티클립 재시작...")
                    restart_handoff = True
                    action_state[0] = "wait"
                    self._active = False
                    if hasattr(self.ui, "_sig_clear_editor"):
                        try:
                            self.ui._sig_clear_editor.emit()
                        except Exception:
                            pass
                    try:
                        self._reuse_existing_multiclip_subtitles = False
                        self._reuse_clip_indices = set()
                        self.ui._reuse_existing_multiclip_subtitles = False
                        self.ui._reuse_clip_indices = set()
                    except Exception:
                        pass
                    if hasattr(self.ui, "_sig_restart_multiclip"):
                        self.ui._sig_restart_multiclip.emit(list(self.files_to_process), self.current_folder)
                    else:
                        threading.Timer(0.05, lambda: self.start_multiclip_pipeline(list(self.files_to_process), self.current_folder)).start()
                    return

                # save 등 다른 action → 정상 종료
                break

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
            if not restart_handoff:
                self._active = False
