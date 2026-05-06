# Version: 03.13.08
# Phase: PHASE2
"""Whisper transcription, ensemble, and STT rescue helpers for VideoProcessor."""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import wave
from concurrent.futures import ThreadPoolExecutor

from core.audio import stt_rescue
from core.performance import adaptive_worker_count
from core.platform_compat import ffmpeg_binary
from core.runtime.logger import get_logger
from core.subtitle_quality.candidate_ranker import rank_overlap_candidates
from core.subtitle_quality.hallucination_detector import annotate_segment_hallucination_risk
from core.subtitle_quality.models import attach_asr_metadata
from core.subtitle_quality.vad_alignment_checker import annotate_segment_vad_alignment


def _parse_worker_json_line(line: str):
    line = (line or "").strip()
    if not line or not line.startswith("{"):
        return None
    try:
        return json.loads(line)
    except Exception as e:
        get_logger().log(f"  ⚠️ JSON 파싱 오류: {e}")
        get_logger().log(f"  ⚠️ raw line: {line[:200] if line else 'empty'}")
        return None


class VideoProcessorTranscribeMixin:
    def _collect_transcribe_result(
        self,
        chunk_dir: str,
        model: str,
        target_end_sec: float = None,
        is_single: bool = False,
        label: str = "STT",
        preview_callback=None,
        settings_overrides: dict | None = None,
    ) -> list[dict]:
        worker = type(self)()
        worker.language = self.language
        if settings_overrides:
            worker._fast_mode_overrides = dict(settings_overrides)
        with self._ensemble_child_lock:
            children = getattr(self, "_ensemble_child_processors", None)
            if not isinstance(children, list):
                children = []
                self._ensemble_child_processors = children
            children.append(worker)
        result: list[dict] = []
        try:
            for chunk_segs, _idx, _total in worker.transcribe(
                chunk_dir,
                is_fast_mode=False,
                target_end_sec=target_end_sec,
                is_single=is_single,
                model_override=model,
                cleanup_chunk_dir=False,
                log_label=label,
                preview_callback=preview_callback,
            ):
                result.extend(chunk_segs or [])
        finally:
            worker.stop_transcribe()
            with self._ensemble_child_lock:
                try:
                    self._ensemble_child_processors.remove(worker)
                except (AttributeError, ValueError):
                    pass
        return result
    @staticmethod
    def _whisper_worker_options(settings: dict) -> dict:
        if not bool((settings or {}).get("stt_rescue_whisper_mode", False)):
            return {}
        return {
            "beam_size": 7,
            "best_of": 7,
            "condition_on_previous_text": False,
            "compression_ratio_threshold": 2.2,
            "log_prob_threshold": -0.85,
            "no_speech_threshold": 0.48,
            "vad_filter": True,
            "vad_parameters": {
                "threshold": 0.35,
                "min_speech_duration_ms": 80,
                "min_silence_duration_ms": 180,
                "speech_pad_ms": 220,
            },
            "hallucination_silence_threshold": 0.6,
        }
    @staticmethod
    def _stt_candidate_keep_score(settings: dict | None) -> float:
        try:
            score = float((settings or {}).get("stt_candidate_keep_score", 24.0) or 24.0)
        except Exception:
            score = 24.0
        return max(0.0, min(100.0, score))
    def _normalize_scored_stt_tracks(
        self,
        tracks: dict[str, list[dict]],
        settings: dict | None,
    ) -> dict[str, list[dict]]:
        from core.audio.stt_candidate_scorer import filter_scored_stt_candidates

        keep_score = self._stt_candidate_keep_score(settings)
        normalized: dict[str, list[dict]] = {}
        for label in ("STT1", "STT2"):
            original = [dict(seg) for seg in (tracks.get(label, []) or []) if isinstance(seg, dict)]
            filtered = filter_scored_stt_candidates(original, min_score=keep_score)
            dropped = len(original) - len(filtered)
            if dropped > 0:
                get_logger().log(
                    f"  🧹 [STT 정리] {label} 저품질 후보 {dropped}개 제외 "
                    f"(유지 기준 {keep_score:.0f}점)"
                )
            normalized[label] = filtered
        return normalized
    def _ensemble_preview_callback(self, label: str, preview_callback):
        if not callable(preview_callback):
            return None
        source_label = str(label or "STT").strip() or "STT"

        def _callback(chunk_segs, _worker_label=None):
            preview = [dict(seg) for seg in (chunk_segs or [])]
            if not preview:
                return
            try:
                preview_callback(preview, source_label)
            except Exception:
                pass

        return _callback
    @staticmethod
    def _segment_chunk_path(segment: dict) -> str:
        meta = dict(segment.get("asr_metadata") or {})
        return str(meta.get("chunk_path") or segment.get("chunk_path") or "")
    @staticmethod
    def _chunk_start_from_path(path: str) -> float:
        name = os.path.basename(str(path or ""))
        match = re.search(r"vad_\d+_([\d.]+)\.wav$", name)
        if not match:
            return 0.0
        try:
            return float(match.group(1))
        except Exception:
            return 0.0
    @staticmethod
    def _wav_duration(path: str) -> float:
        try:
            with wave.open(path, "r") as w:
                return w.getnframes() / float(w.getframerate())
        except Exception:
            return 0.0
    @staticmethod
    def _segment_overlaps_range(segment: dict, start: float, end: float) -> bool:
        seg_start = float(segment.get("start", 0.0) or 0.0)
        seg_end = float(segment.get("end", seg_start) or seg_start)
        overlap = max(0.0, min(seg_end, end) - max(seg_start, start))
        span = max(0.001, min(max(seg_end - seg_start, 0.0), max(end - start, 0.0)))
        return overlap / span >= 0.35
    def _ffmpeg_trim_recheck_clip(self, src_wav: str, out_wav: str, start_sec: float, duration_sec: float) -> bool:
        filter_chain = stt_rescue.rescue_audio_filter()
        cmd = [
            ffmpeg_binary(), "-y", "-nostdin", "-loglevel", "error",
            "-ss", f"{max(0.0, float(start_sec or 0.0)):.3f}",
            "-t", f"{max(0.05, float(duration_sec or 0.05)):.3f}",
            "-i", src_wav,
            "-ac", "1", "-ar", "16000",
            "-af", filter_chain,
            "-acodec", "pcm_s16le",
            out_wav,
        ]
        ok = self._run_media_command_no_progress(cmd, label="STT 재검사 오디오 보정")
        if ok and os.path.exists(out_wav) and os.path.getsize(out_wav) > 0:
            return True
        return self._ffmpeg_trim_to_wav(src_wav, out_wav, start_sec, duration_sec)
    def _prepare_recheck_clip(self, item: stt_rescue.SttRecheckRange, out_dir: str, idx: int, settings: dict) -> dict | None:
        source_path = self._segment_chunk_path(item.primary) or self._segment_chunk_path(item.secondary)
        if not source_path or not os.path.exists(source_path):
            return None

        pad = stt_rescue.recheck_padding(settings)
        chunk_start = self._chunk_start_from_path(source_path)
        chunk_duration = self._wav_duration(source_path)
        abs_start = max(0.0, item.start - pad)
        abs_end = max(abs_start + 0.05, item.end + pad)
        local_start = max(0.0, abs_start - chunk_start)
        local_end = abs_end - chunk_start
        if chunk_duration > 0:
            local_end = min(chunk_duration, local_end)
        duration = max(0.05, local_end - local_start)
        if duration <= 0.05:
            return None

        actual_abs_start = chunk_start + local_start
        out_path = os.path.join(out_dir, f"vad_{900 + idx:03d}_{actual_abs_start:.3f}.wav")
        if not self._ffmpeg_trim_recheck_clip(source_path, out_path, local_start, duration):
            return None
        return {
            "range": item,
            "path": out_path,
            "start": round(actual_abs_start, 3),
            "end": round(actual_abs_start + duration, 3),
        }
    def _recheck_low_score_stt_ranges(
        self,
        chunk_dir: str,
        results: dict[str, list[dict]],
        settings: dict,
        vad_strict: list[dict],
        primary_model: str,
    ) -> dict[str, list[dict]]:
        if not stt_rescue.enabled(settings):
            return results

        ranges = stt_rescue.find_low_score_recheck_ranges(
            results.get("STT1", []),
            results.get("STT2", []),
            settings,
        )
        if not ranges:
            return results

        threshold = stt_rescue.threshold(settings)
        get_logger().log(
            f"  🔁 [STT 재검사] STT1/STT2 모두 {threshold:.0f}점 이하인 구간 {len(ranges)}개 재인식 시작"
        )
        self._notify_stage(f"⏳ [STT] 저점 구간 {len(ranges)}개 재검사 중")

        rescue_dir = os.path.join(chunk_dir, "_stt_recheck")
        os.makedirs(rescue_dir, exist_ok=True)
        prepared: list[dict] = []
        for idx, item in enumerate(ranges):
            clip = self._prepare_recheck_clip(item, rescue_dir, idx, settings)
            if clip:
                prepared.append(clip)
        if not prepared:
            get_logger().log("  ⚠️ [STT 재검사] 재검사용 WAV 생성 실패로 기존 후보를 유지합니다.")
            return results

        rescue_model = str(settings.get("stt_low_score_recheck_model") or primary_model or "").strip() or primary_model
        overrides = {
            "stt_ensemble_enabled": False,
            "stt_candidate_scoring_enabled": True,
            "stt_quality_preset": "precise",
            "stt_rescue_whisper_mode": True,
            "w_none_temp_max": 0.0,
            "whisper_chunk_overlap_sec": 0.0,
        }
        rescue_segments = self._collect_transcribe_result(
            rescue_dir,
            rescue_model,
            is_single=False,
            label="STT-재검사",
            settings_overrides=overrides,
        )
        if not rescue_segments:
            get_logger().log("  ⚠️ [STT 재검사] 재인식 결과가 비어 있어 기존 후보를 유지합니다.")
            return results

        try:
            from core.audio.stt_candidate_scorer import annotate_stt_candidates

            rescue_segments = annotate_stt_candidates(
                rescue_segments,
                source="RECHECK",
                vad_segments=vad_strict,
                settings=settings,
            )
        except Exception as exc:
            get_logger().log(f"  ⚠️ [STT 재검사] 재검사 점수 계산 실패: {exc}")

        applied_ranges: list[stt_rescue.SttRecheckRange] = []
        applied_segments: list[dict] = []
        for clip in prepared:
            item = clip["range"]
            start = float(clip["start"])
            end = float(clip["end"])
            subset = [
                dict(seg)
                for seg in rescue_segments
                if self._segment_overlaps_range(seg, start, end)
            ]
            if not stt_rescue.replacement_is_better(subset, item, settings):
                get_logger().log(
                    "  ↩️ [STT 재검사] 개선 부족으로 기존 후보 유지 "
                    f"({item.start:.2f}-{item.end:.2f}s, STT1 {item.primary_score:.1f}, STT2 {item.secondary_score:.1f})"
                )
                continue
            marked = stt_rescue.mark_rescue_segments(subset, item)
            for seg in marked:
                seg["stt_selected_source"] = "RECHECK"
                seg["stt_ensemble_source"] = "RECHECK"
            applied_ranges.append(item)
            applied_segments.extend(marked)

        if not applied_segments:
            get_logger().log("  ↩️ [STT 재검사] 교체할 만큼 좋아진 구간이 없어 기존 후보를 유지합니다.")
            return results

        def _keep_existing(seg: dict) -> bool:
            return not any(self._segment_overlaps_range(seg, item.start, item.end) for item in applied_ranges)

        reapplied_segments = [dict(seg) for seg in applied_segments]
        for seg in reapplied_segments:
            seg["stt_selected_source"] = "RECHECK"
            seg["stt_ensemble_source"] = "RECHECK"
        updated = {
            "STT1": [seg for seg in results.get("STT1", []) if _keep_existing(seg)] + applied_segments,
            "STT2": [seg for seg in results.get("STT2", []) if _keep_existing(seg)] + reapplied_segments,
        }
        updated["STT1"].sort(key=lambda seg: (float(seg.get("start", 0.0) or 0.0), float(seg.get("end", 0.0) or 0.0)))
        updated["STT2"].sort(key=lambda seg: (float(seg.get("start", 0.0) or 0.0), float(seg.get("end", 0.0) or 0.0)))
        get_logger().log(f"  ✅ [STT 재검사] {len(applied_ranges)}개 저점 구간을 재인식 결과로 교체했습니다.")
        return updated
    def transcribe_ensemble(
        self,
        chunk_dir: str,
        target_end_sec: float = None,
        is_single: bool = False,
        preview_callback=None,
    ):
        s = self._load_all_settings()
        primary_model = s.get("selected_whisper_model", self.whisper_model)
        secondary_model = s.get("selected_whisper_model_secondary", "")
        if not secondary_model or secondary_model == primary_model:
            yield from self.transcribe(
                chunk_dir,
                is_fast_mode=False,
                target_end_sec=target_end_sec,
                is_single=is_single,
                model_override=primary_model,
                cleanup_chunk_dir=True,
                log_label="STT1",
                preview_callback=preview_callback,
            )
            return

        get_logger().log(
            "\n🎧 [STT 앙상블] STT1/STT2 병렬 인식 시작 "
            f"(STT1: {primary_model.split(chr(47))[-1]}, STT2: {secondary_model.split(chr(47))[-1]})"
        )
        self._notify_stage("⏳ [STT] STT1/STT2 병렬 인식 중")
        results: dict[str, list[dict]] = {"STT1": [], "STT2": []}
        errors: dict[str, BaseException] = {}
        result_lock = threading.Lock()
        error_lock = threading.Lock()

        def _run(label: str, model: str):
            try:
                local_result = self._collect_transcribe_result(
                    chunk_dir,
                    model,
                    target_end_sec=target_end_sec,
                    is_single=is_single,
                    label=label,
                    preview_callback=self._ensemble_preview_callback(label, preview_callback),
                )
                with result_lock:
                    results[label] = local_result
            except BaseException as exc:
                with error_lock:
                    errors[label] = exc

        try:
            stt_workers, scheduler_meta = adaptive_worker_count(
                task="stt",
                settings=s,
                requested=2,
                workload=2,
                minimum=1,
                maximum=2,
            )
            reductions = ",".join(scheduler_meta.get("reductions") or [])
            suffix = f" ({reductions})" if reductions else ""
            get_logger().log(f"  🧵 [STT 앙상블] 리소스 자동 스케줄러: {stt_workers}개 워커{suffix}")
            with ThreadPoolExecutor(max_workers=stt_workers, thread_name_prefix="stt-ensemble") as executor:
                futures = [
                    executor.submit(_run, "STT1", primary_model),
                    executor.submit(_run, "STT2", secondary_model),
                ]
                for future in futures:
                    future.result()
            for label, exc in errors.items():
                get_logger().log(f"  ⚠️ [STT 앙상블] {label} 인식 실패: {exc}")
            if not results["STT1"] and not results["STT2"]:
                raise RuntimeError("STT 앙상블 결과가 비어 있습니다")
            vad_strict = []
            vad_json = os.path.join(chunk_dir, "vad_strict.json")
            if os.path.exists(vad_json):
                try:
                    with open(vad_json, "r", encoding="utf-8") as f:
                        vad_strict = json.load(f)
                except Exception:
                    vad_strict = []
            scoring_enabled = True
            if scoring_enabled:
                try:
                    from core.audio.stt_candidate_scorer import (
                        annotate_stt_candidate_tracks,
                        average_stt_score,
                    )

                    scored_tracks = annotate_stt_candidate_tracks(
                        {"STT1": results["STT1"], "STT2": results["STT2"]},
                        vad_segments=vad_strict,
                        settings=s,
                    )
                    results["STT1"] = scored_tracks.get("STT1", results["STT1"])
                    results["STT2"] = scored_tracks.get("STT2", results["STT2"])
                    results = self._normalize_scored_stt_tracks(results, s)
                    get_logger().log(
                        "  📊 [STT 점수] "
                        f"STT1 평균 {average_stt_score(results['STT1']):.1f}점 / "
                        f"STT2 평균 {average_stt_score(results['STT2']):.1f}점"
                    )
                except Exception as exc:
                    get_logger().log(f"  ⚠️ [STT 점수] 후보 점수 계산 실패, 기존 병합 유지: {exc}")

            try:
                if scoring_enabled:
                    results = self._recheck_low_score_stt_ranges(
                        chunk_dir,
                        results,
                        s,
                        vad_strict,
                        primary_model,
                    )
                    from core.audio.stt_candidate_scorer import annotate_stt_candidate_tracks

                    rescored_tracks = annotate_stt_candidate_tracks(
                        {"STT1": results["STT1"], "STT2": results["STT2"]},
                        vad_segments=vad_strict,
                        settings=s,
                    )
                    results["STT1"] = rescored_tracks.get("STT1", results["STT1"])
                    results["STT2"] = rescored_tracks.get("STT2", results["STT2"])
                    results = self._normalize_scored_stt_tracks(results, s)
            except Exception as exc:
                get_logger().log(f"  ⚠️ [STT 재검사] 오류로 기존 STT 후보를 유지합니다: {exc}")

            from core.audio.stt_ensemble import merge_stt_outputs

            merged = merge_stt_outputs(results["STT1"], results["STT2"])
            if vad_strict and bool(s.get("vad_post_stt_align_enabled", True)):
                from core.subtitle_quality.vad_alignment_checker import adjust_segments_to_vad_boundaries

                self._notify_stage("⏳ [VAD] 앙상블 자막 위치 재계산 중")
                merged, adjusted_count = adjust_segments_to_vad_boundaries(
                    merged,
                    vad_strict,
                    max_shift_sec=float(s.get("vad_post_stt_max_shift_sec", 0.7) or 0.7),
                    edge_pad_sec=float(s.get("vad_post_stt_edge_pad_sec", 0.04) or 0.04),
                )
                get_logger().log(f"  🎯 [VAD 후처리] 앙상블 자막 위치 {adjusted_count}개 보정")
            get_logger().log(
                "  ✅ [STT 앙상블] 후보 병합 완료 "
                f"(STT1 {len(results['STT1'])}개 / STT2 {len(results['STT2'])}개 → {len(merged)}개, "
                "단어 단위 ROVER · 저신뢰 STT1 구간 STT2 보강)"
            )
            yield merged, 1, 1
        finally:
            shutil.rmtree(chunk_dir, ignore_errors=True)
    def transcribe(
        self,
        chunk_dir: str,
        is_fast_mode: bool = False,
        target_end_sec: float = None,
        is_single: bool = False,
        model_override: str | None = None,
        cleanup_chunk_dir: bool = True,
        log_label: str = "STT",
        preview_callback=None,
    ):
        _ = is_fast_mode
        chunks = sorted([f for f in os.listdir(chunk_dir) if f.endswith(".wav")])
        if not chunks:
            yield [], 0, 0
            return

        vad_strict = []
        vad_json = os.path.join(chunk_dir, "vad_strict.json")
        if os.path.exists(vad_json):
            try:
                with open(vad_json, "r", encoding="utf-8") as f:
                    vad_strict = json.load(f)
            except Exception:
                pass

        total = len(chunks)
        _s = self._load_all_settings()
        if model_override is None and bool(_s.get("stt_ensemble_enabled", False)):
            yield from self.transcribe_ensemble(
                chunk_dir,
                target_end_sec=target_end_sec,
                is_single=is_single,
                preview_callback=preview_callback,
            )
            return
        target_model = model_override or _s.get("selected_whisper_model", self.whisper_model)
        self._notify_stage(f"⏳ [{log_label}] Whisper 인식 중")
        get_logger().log(f"\n🎯 [{log_label}] Whisper 인식 시작 (총 {total}블록, 모델: {target_model.split(chr(47))[-1]})")

        t_sec = 1.0
        q = []
        for i, cf in enumerate(chunks):
            cp = os.path.join(chunk_dir, cf)
            m = re.search(r'vad_\d+_([\d\.]+)\.wav', cf)
            ov_start = float(m.group(1)) if m else i * 30.0
            q.append({
                "idx": i,
                "input_path": cp,
                "ov_start_offset": ov_start
            })
            if i == len(chunks) - 1:
                try:
                    with wave.open(cp, "r") as w:
                        t_sec = ov_start + (w.getnframes() / float(w.getframerate()))
                except Exception:
                    t_sec = ov_start + 30.0

        safe_paths = [x["input_path"] for x in q]
        s = self._load_all_settings()
        temp_max = float(s.get("w_none_temp_max", 0.4))
        temperature_values = [round(x * 0.2, 1) for x in range(int(temp_max / 0.2) + 1)]
        temperature_tuple = "(" + ", ".join(str(x) for x in temperature_values) + ",)"

        from core.runtime import config as _cfg

        mac_task_id = None
        from core.audio.whisper_coreml import is_coreml_whisper_model
        from core.audio.whisper_transformers import is_transformers_whisper_model

        use_coreml_whisper = is_coreml_whisper_model(target_model)
        use_transformers_whisper = is_transformers_whisper_model(target_model)
        if use_coreml_whisper:
            from core.audio.whisper_coreml import run_whisper
            proc = run_whisper(
                chunk_paths=safe_paths,
                model=target_model,
                language=self.language,
                temperature_tuple=temperature_tuple,
                log_label=log_label,
                options=self._whisper_worker_options(s),
            )
            if proc is None:
                fallback_model = "mlx-community/whisper-large-v3-turbo"
                get_logger().log(f"  ↩️ [{log_label}] Core ML STT 준비 안 됨 → MLX fallback: {fallback_model}")
                target_model = fallback_model
                use_coreml_whisper = False
        if use_transformers_whisper:
            from core.audio.whisper_transformers import run_whisper
            proc = run_whisper(
                chunk_paths=safe_paths,
                model=target_model,
                language=self.language,
                temperature_tuple=temperature_tuple,
                log_label=log_label,
            )
            if proc is None:
                get_logger().log("❌ Transformers Whisper 백엔드를 실행할 수 없습니다.")
                return
        elif use_coreml_whisper:
            pass
        elif _cfg.IS_MAC:
            from core.audio.whisper_mlx import ensure_worker, submit_task

            with self._whisper_lock:
                self._whisper_runner_proc = ensure_worker(self._whisper_runner_proc)
                proc = self._whisper_runner_proc
                mac_task_id = submit_task(
                    proc=proc,
                    chunk_paths=safe_paths,
                    model=target_model,
                    language=self.language,
                    temperature_values=temperature_values
                )
        else:
            from core.audio.whisper_faster import run_whisper
            proc = run_whisper(
                chunk_paths=safe_paths,
                model=target_model,
                language=self.language,
                temperature_tuple=temperature_tuple,
                log_label=log_label,
            )
            if proc is None:
                get_logger().log("❌ Whisper 백엔드를 실행할 수 없습니다.")
                return

        self._whisper_proc = proc
        prev_end = 0.0
        had_error = False
        processed_count = 0

        try:
            if _cfg.IS_MAC and not use_coreml_whisper and not use_transformers_whisper:
                received = 0
                while received < total:
                    line = proc.stdout.readline()
                    if not line:
                        break

                    data = _parse_worker_json_line(line)
                    if data is None:
                        continue

                    if data.get("task_id") != mac_task_id:
                        continue
                    if data.get("done"):
                        break

                    if data.get("fatal_error") or data.get("error"):
                        had_error = True
                        msg = data.get("fatal_error") or data.get("error") or "unknown whisper worker error"
                        stage = data.get("stage", "worker")
                        get_logger().log(f"  [FAIL] Whisper worker error ({stage}): {msg}")
                        raise RuntimeError(f"whisper_worker_error[{stage}]: {msg}")

                    idx = int(data.get("index", received))
                    item = q[idx]
                    payload = data.get("result") if "result" in data else {"error": data.get("error", "")}
                    if isinstance(payload, dict):
                        payload.setdefault("backend", data.get("backend", "mlx-whisper"))
                        payload.setdefault("language_probability", data.get("language_probability"))
                        payload.setdefault("chunk_path", item.get("input_path"))
                    chunk_segs = self._parse_whisper_payload(
                        payload,
                        item,
                        vad_strict,
                        target_end_sec=target_end_sec,
                        is_single=is_single
                    )
                    chunk_segs = self._dedupe_overlapping_segments(
                        chunk_segs,
                        previous_end=prev_end,
                        dedup_window=float(s.get("sub_dedup_window", 0.5) or 0.5),
                        vad_segments=vad_strict,
                    )

                    if chunk_segs:
                        prev_end = chunk_segs[-1]["end"]
                        if callable(preview_callback):
                            try:
                                preview_callback(chunk_segs, log_label)
                            except Exception:
                                pass

                    pct = min(100, int((prev_end / t_sec) * 100))
                    get_logger().log(self._format_transcribe_progress(log_label, prev_end, t_sec, pct))

                    yield chunk_segs, item["idx"] + 1, total
                    processed_count += 1
                    received += 1

            else:
                for item in q:
                    line = proc.stdout.readline()
                    if not line:
                        break

                    data = _parse_worker_json_line(line)
                    if data is None:
                        continue

                    if data.get("fatal_error") or data.get("error"):
                        had_error = True
                        msg = data.get("fatal_error") or data.get("error") or "unknown whisper worker error"
                        stage = data.get("stage", "worker")
                        get_logger().log(f"  [FAIL] Whisper worker error ({stage}): {msg}")
                        raise RuntimeError(f"whisper_worker_error[{stage}]: {msg}")

                    chunk_segs = self._parse_whisper_payload(
                        data,
                        item,
                        vad_strict,
                        target_end_sec=target_end_sec,
                        is_single=is_single
                    )
                    chunk_segs = self._dedupe_overlapping_segments(
                        chunk_segs,
                        previous_end=prev_end,
                        dedup_window=float(s.get("sub_dedup_window", 0.5) or 0.5),
                        vad_segments=vad_strict,
                    )

                    if chunk_segs:
                        prev_end = chunk_segs[-1]["end"]
                        if callable(preview_callback):
                            try:
                                preview_callback(chunk_segs, log_label)
                            except Exception:
                                pass

                    pct = min(100, int((prev_end / t_sec) * 100))
                    get_logger().log(self._format_transcribe_progress(log_label, prev_end, t_sec, pct))
                    yield chunk_segs, item["idx"] + 1, total
                    processed_count += 1

                proc.wait()
                if proc.returncode not in (0, None):
                    had_error = True
                    raise RuntimeError(f"whisper_worker_exit_code={proc.returncode}")
                if processed_count == 0 and total > 0:
                    had_error = True
                    raise RuntimeError("whisper produced 0 chunks")

        finally:
            self._whisper_proc = None
            if cleanup_chunk_dir:
                shutil.rmtree(chunk_dir, ignore_errors=True)
            if had_error:
                get_logger().log(f"[WARN] {log_label} Whisper transcription aborted due to worker failure")
            else:
                get_logger().log(f"[DONE] {log_label} Whisper transcription completed")
    @staticmethod
    def _format_transcribe_progress(log_label: str, current_sec: float, total_sec: float, pct: int) -> str:
        label = (log_label or "STT").strip() or "STT"
        return (
            f"  ▶ [{label}] 진행 상황: {int(current_sec // 60):02d}분 {int(current_sec % 60):02d}초 / "
            f"{int(total_sec // 60):02d}분 {int(total_sec % 60):02d}초 ({int(pct)}%)"
        )
    def stop_transcribe(self):
        try:
            with getattr(self, "_ensemble_child_lock", threading.Lock()):
                children = list(getattr(self, "_ensemble_child_processors", []) or [])
            for child in children:
                try:
                    child.stop_transcribe()
                except Exception:
                    pass

            from core.runtime import config as _cfg

            if _cfg.IS_MAC:
                from core.audio.whisper_mlx import stop_worker
                with self._whisper_lock:
                    if self._whisper_runner_proc:
                        stop_worker(self._whisper_runner_proc)
                        self._whisper_runner_proc = None
                    self._whisper_proc = None
                return

            if self._whisper_proc and self._whisper_proc.poll() is None:
                self._whisper_proc.terminate()
                try:
                    self._whisper_proc.wait(timeout=2)
                except Exception:
                    self._whisper_proc.kill()

        except Exception:
            pass
        finally:
            self._whisper_proc = None
    def release_runtime_models(self):
        self.stop_transcribe()
        try:
            with getattr(self, "_ensemble_child_lock", threading.Lock()):
                children = list(getattr(self, "_ensemble_child_processors", []) or [])
            for child in children:
                try:
                    if hasattr(child, "release_runtime_models"):
                        child.release_runtime_models()
                except Exception:
                    pass
            with getattr(self, "_ensemble_child_lock", threading.Lock()):
                self._ensemble_child_processors = []
        except Exception:
            pass
        try:
            self._vad_model = None
            self._vad_utils = None
            self._vad_loaded = False
        except Exception:
            pass
        try:
            import gc

            gc.collect()
        except Exception:
            pass
        try:
            import torch

            if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
                torch.mps.empty_cache()
            if hasattr(torch, "cuda") and torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
    def _parse_whisper_payload(self, data: dict, item: dict, vad_strict: list,
                           target_end_sec: float = None, is_single: bool = False) -> list[dict]:
        chunk_segs = []
        if "segments" not in data:
            if data.get("error"):
                get_logger().log(f"  ⚠️ Whisper 오류: {data.get('error')}")
            return chunk_segs

        offset = item["ov_start_offset"]

        for seg in data["segments"]:
            words = seg.get("words", [])
            exact_start = seg["start"] + offset
            exact_end = seg["end"] + offset
            offset_words = []

            if words:
                valid_words = [
                    w for w in words
                    if "start" in w and "end" in w and w.get("word", "").strip()
                ]

                word_filter_vad = [v for v in vad_strict if v.get("vad_word_filter", True)]
                if word_filter_vad:
                    temp_words = []
                    for w in valid_words:
                        w_start = w["start"] + offset
                        w_end = w["end"] + offset
                        is_valid = False
                        for v in word_filter_vad:
                            if w_start <= v["end"] + 0.5 and w_end >= v["start"] - 0.5:
                                is_valid = True
                                break
                        if is_valid:
                            temp_words.append(w)
                    valid_words = temp_words

                if valid_words:
                    exact_start = valid_words[0]["start"] + offset
                    exact_end = valid_words[-1]["end"] + offset
                    for w in valid_words:
                        word_item = {
                            "word": w.get("word", ""),
                            "start": w["start"] + offset,
                            "end": w["end"] + offset
                        }
                        for conf_key in ("confidence", "probability", "score"):
                            if conf_key in w:
                                word_item[conf_key] = w.get(conf_key)
                        offset_words.append(word_item)

            if words and not offset_words:
                continue

            if is_single and target_end_sec is not None:
                if exact_start >= target_end_sec:
                    continue
                if exact_end > target_end_sec:
                    exact_end = target_end_sec

            segment = {
                "start": exact_start,
                "end": exact_end,
                "text": seg.get("text", "").strip(),
                "words": offset_words,
            }
            for key in (
                "avg_logprob",
                "compression_ratio",
                "no_speech_prob",
                "temperature",
                "tokens",
                "word_confidence",
            ):
                if key in seg:
                    segment[key] = seg.get(key)
            segment = attach_asr_metadata(
                segment,
                backend=data.get("backend"),
                language_probability=data.get("language_probability"),
                chunk_path=data.get("chunk_path") or item.get("input_path"),
            )
            if vad_strict:
                segment = annotate_segment_vad_alignment(segment, vad_strict)
            segment = annotate_segment_hallucination_risk(segment, vad_segments=vad_strict)
            chunk_segs.append(segment)

        return chunk_segs
    def _dedupe_overlapping_segments(
        self,
        chunk_segs: list[dict],
        previous_end: float,
        dedup_window: float = 0.5,
        vad_segments: list[dict] | None = None,
    ) -> list[dict]:
        if not chunk_segs or previous_end <= 0.0:
            return chunk_segs

        boundary = max(0.0, float(previous_end) - min(max(float(dedup_window or 0.0), 0.0), 0.15))
        cleaned = []
        for seg in chunk_segs:
            words = [
                dict(w)
                for w in (seg.get("words") or [])
                if float(w.get("end", 0.0) or 0.0) > boundary
            ]
            if seg.get("words"):
                if not words:
                    continue
                trimmed = dict(seg)
                trimmed["words"] = words
                trimmed["start"] = float(words[0].get("start", seg.get("start", previous_end)) or previous_end)
                trimmed["end"] = float(words[-1].get("end", seg.get("end", previous_end)) or previous_end)
                if words and words != seg.get("words"):
                    text = " ".join(str(w.get("word", "") or "").strip() for w in words).strip()
                    if text:
                        trimmed["text"] = text
                    trimmed = attach_asr_metadata(trimmed, backend=(trimmed.get("asr_metadata") or {}).get("backend"))
                    if vad_segments:
                        trimmed = annotate_segment_vad_alignment(trimmed, vad_segments)
                    trimmed = annotate_segment_hallucination_risk(trimmed, vad_segments=vad_segments or [])

                ranked = rank_overlap_candidates(
                    [
                        {"candidate_id": "original", "segment": seg},
                        {"candidate_id": "trimmed", "segment": trimmed, "score_bonus": 2.0},
                    ],
                    vad_segments=vad_segments or [],
                    previous_end=previous_end,
                )
                selected_id = str(ranked[0].get("candidate_id") or "trimmed")
                selected_score = ranked[0].get("score")
                selected = dict(ranked[0].get("segment") or trimmed)
                if selected.get("start", 0.0) < previous_end and trimmed.get("end", 0.0) > trimmed.get("start", 0.0):
                    selected = trimmed
                    selected_id = "trimmed"
                    for item in ranked:
                        if item.get("candidate_id") == "trimmed":
                            selected_score = item.get("score")
                            break
                asr_metadata = dict(selected.get("asr_metadata") or {})
                asr_metadata["overlap_candidate"] = {
                    "selected": selected_id,
                    "score": selected_score,
                    "boundary": round(boundary, 6),
                }
                selected["asr_metadata"] = asr_metadata
                cleaned.append(selected)
                continue

            exact_end = float(seg.get("end", 0.0) or 0.0)
            if exact_end <= boundary:
                continue
            new_seg = dict(seg)
            new_seg["start"] = max(float(new_seg.get("start", 0.0) or 0.0), previous_end)
            if new_seg["end"] > new_seg["start"]:
                if vad_segments:
                    new_seg = annotate_segment_vad_alignment(new_seg, vad_segments)
                new_seg = annotate_segment_hallucination_risk(new_seg, vad_segments=vad_segments or [])
                cleaned.append(new_seg)

        return cleaned
