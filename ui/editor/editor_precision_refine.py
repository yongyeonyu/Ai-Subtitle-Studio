"""Manual precision subtitle refinement actions for EditorWidget."""

from __future__ import annotations

import os
import threading
import time
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox

from core.engine.subtitle_post_llm import run_subtitle_post_llm_action
from core.runtime.logger import get_logger
from core.subtitle_quality.precision_vad_lattice import build_precision_vad_lattice_for_media
from core.subtitle_quality.quality_pipeline import run_subtitle_quality_pipeline
from core.subtitle_quality.selective_precision_whisper import run_selective_precision_whisper
from core.subtitle_quality.timestamp_regrouper import refine_segment_edges_with_context
from core.subtitle_quality.vad_alignment_checker import normalize_vad_segments
from ui.dialogs.message_box import show_message
from ui.editor.ux.editor_subtitle_assist import (
    apply_netflix_subtitle_magnet,
    compute_subtitle_magnet_policy,
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _segment_signature(segment: dict[str, Any], index: int) -> tuple:
    return (
        int(segment.get("line", index) if segment.get("line") is not None else index),
        round(_safe_float(segment.get("start")), 3),
        round(_safe_float(segment.get("end")), 3),
        str(segment.get("text", "") or ""),
        str(segment.get("speaker", segment.get("spk", "")) or ""),
    )


def _changed_count(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> int:
    count = 0
    total = max(len(before), len(after))
    for idx in range(total):
        left = before[idx] if idx < len(before) else {}
        right = after[idx] if idx < len(after) else {}
        if _segment_signature(left, idx) != _segment_signature(right, idx):
            count += 1
    return count


def _merge_vad_rows(rows: list[dict[str, Any]], *, merge_gap_sec: float = 0.05) -> list[dict[str, Any]]:
    vad = sorted(normalize_vad_segments(rows), key=lambda item: (item["start"], item["end"]))
    merged: list[dict[str, Any]] = []
    for row in vad:
        if not merged or row["start"] > merged[-1]["end"] + max(0.0, float(merge_gap_sec)):
            merged.append(dict(row))
            continue
        merged[-1]["end"] = max(merged[-1]["end"], row["end"])
    return merged


def _precision_clip_boundaries(rows: list[Any] | tuple[Any, ...] | None) -> list[dict[str, Any]]:
    boundaries: list[dict[str, Any]] = []
    for row in list(rows or []):
        if not isinstance(row, dict):
            continue
        if row.get("start") is None or row.get("end") is None:
            continue
        start = _safe_float(row.get("start"))
        end = _safe_float(row.get("end"), start)
        if end <= start:
            continue
        item = dict(row)
        item["start"] = start
        item["end"] = end
        boundaries.append(item)
    return boundaries


def _precision_dialog_parent(owner: Any):
    try:
        window = owner.window()
        return window or owner
    except Exception:
        return owner


def _precision_media_label(path: Any) -> str:
    text = str(path or "").strip()
    if not text:
        return "-"
    return os.path.basename(text) or text


def _precision_debug_value(value: Any) -> str:
    if isinstance(value, dict):
        parts = []
        for key in sorted(value):
            item = value.get(key)
            if isinstance(item, (list, tuple, set)):
                item = len(item)
            parts.append(f"{key}={item}")
        return "{" + ", ".join(parts) + "}"
    if isinstance(value, (list, tuple, set)):
        return "[" + ", ".join(str(item) for item in list(value)[:12]) + (", ..." if len(value) > 12 else "") + "]"
    return str(value)


def _precision_normalize_llm_route(provider: Any, model: Any) -> tuple[str, str] | None:
    provider_key = str(provider or "ollama").strip().lower()
    model_name = str(model or "").strip()
    if provider_key in {"", "inherit"}:
        provider_key = "ollama"
    if provider_key == "none" or not model_name or "사용 안함" in model_name:
        return None
    return provider_key, model_name


def _precision_resolve_spellcheck_llm(settings: dict[str, Any] | None) -> tuple[str, str] | None:
    current = dict(settings or {})
    selected = _precision_normalize_llm_route(
        current.get("selected_llm_provider", "ollama"),
        current.get("selected_model", ""),
    )
    if selected is not None:
        return selected
    roughcut_provider = current.get("roughcut_llm_provider", current.get("selected_llm_provider", "ollama"))
    roughcut_model = current.get("roughcut_llm_model", "")
    if str(roughcut_provider or "").strip().lower() == "inherit":
        roughcut_provider = current.get("selected_llm_provider", "ollama")
    if str(roughcut_model or "").strip() in {"", "inherit"}:
        roughcut_model = current.get("selected_model", "")
    return _precision_normalize_llm_route(roughcut_provider, roughcut_model)


def _run_precision_full_text_correction(
    segments: list[dict[str, Any]],
    *,
    settings: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    resolved = _precision_resolve_spellcheck_llm(settings)
    if resolved is None:
        raise RuntimeError("정밀 작업에 사용할 자막 LLM이 설정되어 있지 않습니다.")
    provider, model = resolved
    current = dict(settings or {})
    batch_size = max(1, int(current.get("precision_spellcheck_batch_size", 60) or 60))
    timeout = max(30, int(current.get("precision_spellcheck_timeout_sec", 240) or 240))
    corrected, changed = run_subtitle_post_llm_action(
        "spellcheck",
        segments,
        provider=provider,
        model=model,
        batch_size=batch_size,
        timeout=timeout,
    )
    return (
        [dict(seg) for seg in list(corrected or []) if isinstance(seg, dict)],
        {
            "provider": provider,
            "model": model,
            "batch_size": batch_size,
            "timeout": timeout,
            "changed_count": int(changed or 0),
        },
    )


def _precision_log(message: str, *, level: str = "INFO") -> None:
    try:
        get_logger().log(f"🔎 [정밀 자막] {message}", level=level, stage="precision")
    except Exception:
        pass


def _precision_debug(message: str, **fields: Any) -> None:
    try:
        detail = " · ".join(
            f"{key}={_precision_debug_value(value)}"
            for key, value in fields.items()
            if value not in (None, "")
        )
        suffix = f" · {detail}" if detail else ""
        get_logger().terminal_debug(f"🔎 [정밀 자막 디버그] {message}{suffix}", stage="precision")
    except Exception:
        pass


def _precision_status(callback, text: str) -> None:
    if not callable(callback):
        return
    try:
        callback(str(text or ""))
    except Exception:
        pass


def _precision_log_failure(
    exc: BaseException,
    *,
    started_at: float,
    before_count: int = 0,
    final_count: int = 0,
) -> None:
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    _precision_log(f"실패: {type(exc).__name__}: {exc}", level="ERROR")
    _precision_debug(
        "run failed",
        elapsed_ms=round(elapsed_ms, 1),
        error_type=type(exc).__name__,
        error=str(exc),
        before_count=before_count,
        final_count=final_count,
    )


class _PrecisionRefineBridge(QObject):
    progress = pyqtSignal(str)
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(object)


def _precision_compute_refinement_job(job: dict[str, Any], *, status_callback=None) -> dict[str, Any]:
    started_at = time.perf_counter()
    before = [dict(seg) for seg in list(job.get("before") or []) if isinstance(seg, dict)]
    final_segments: list[dict[str, Any]] = []
    media_path = str(job.get("media_path") or "")
    fps = _safe_float(job.get("fps"), 30.0)
    existing_vad_segments = [dict(row) for row in list(job.get("existing_vad_segments") or []) if isinstance(row, dict)]
    existing_voice_activity_segments = [
        dict(row) for row in list(job.get("existing_voice_activity_segments") or []) if isinstance(row, dict)
    ]
    boundary_times = list(job.get("boundary_times") or [])
    provisional_boundaries = list(job.get("provisional_boundaries") or [])
    clip_boundaries = [dict(row) for row in list(job.get("clip_boundaries") or []) if isinstance(row, dict)]
    audio_paths = dict(job.get("audio_paths") or {})
    video_processor = job.get("video_processor")
    settings = dict(job.get("settings") or {})

    _precision_log(f"시작: 정밀 작업 실행 · 자막 {len(before)}개 · media={_precision_media_label(media_path)}")
    _precision_debug(
        "run start",
        media_path=media_path,
        fps=fps,
        segment_count=len(before),
        first_start=round(_safe_float(before[0].get("start")), 3) if before else None,
        last_end=round(_safe_float(before[-1].get("end")), 3) if before else None,
    )
    _precision_status(status_callback, "정밀 음성 경계 분석 중...")

    _precision_log(
        "VAD lattice 분석 시작: "
        f"기존 VAD {len(existing_vad_segments)}개 · voice {len(existing_voice_activity_segments)}개"
    )
    _precision_debug(
        "vad lattice input",
        existing_vad_count=len(existing_vad_segments),
        existing_voice_activity_count=len(existing_voice_activity_segments),
        boundary_count=len(boundary_times),
        provisional_count=len(provisional_boundaries),
        clip_boundary_count=len(clip_boundaries),
        audio_paths=audio_paths,
        has_video_processor=video_processor is not None,
    )
    lattice_result = build_precision_vad_lattice_for_media(
        media_path,
        settings=settings,
        existing_vad_segments=existing_vad_segments,
        existing_voice_activity_segments=existing_voice_activity_segments,
        audio_paths=audio_paths,
        video_processor=video_processor,
    )
    vad_segments = list(lattice_result.segments or ())
    if not vad_segments:
        vad_segments = _merge_vad_rows(existing_vad_segments + existing_voice_activity_segments)
    _precision_log(f"VAD lattice 완료: 음성 경계 {len(vad_segments)}개")
    _precision_debug(
        "vad lattice done",
        vad_count=len(vad_segments),
        source_counts=dict(getattr(lattice_result, "source_counts", {}) or {}),
        resolved_audio_paths=dict(lattice_result.audio_paths or {}),
        report=dict(lattice_result.report or {}),
    )

    _precision_status(status_callback, "정밀 전체 텍스트 교정 중...")
    _precision_log("전체 자막 맞춤법/띄어쓰기/단어 교정 시작")
    spellchecked, spellcheck_report = _run_precision_full_text_correction(before, settings=settings)
    _precision_log(
        "전체 자막 맞춤법/띄어쓰기/단어 교정 완료: "
        f"변경 {int(spellcheck_report.get('changed_count', 0) or 0)}개 · "
        f"provider={spellcheck_report.get('provider', '-')} · model={spellcheck_report.get('model', '-')}"
    )
    _precision_debug("full text correction done", report=spellcheck_report)

    _precision_status(status_callback, "정밀 자막 품질/타이밍 보정 중...")
    _precision_log("맞춤법/띄어쓰기/품질 보정 시작")
    quality_result = run_subtitle_quality_pipeline(
        spellchecked,
        vad_segments=vad_segments,
        settings=settings,
        auto_correct=True,
        context={"clip_boundaries": clip_boundaries},
    )
    corrected = [dict(seg) for seg in list(getattr(quality_result, "segments", []) or [])]
    quality_summary = getattr(quality_result, "summary", None)
    _precision_log(f"맞춤법/띄어쓰기/품질 보정 완료: 자막 {len(corrected)}개")
    _precision_debug(
        "quality pipeline done",
        corrected_count=len(corrected),
        overall_score=getattr(quality_summary, "overall_score", None),
        clip_boundary_count=len(clip_boundaries),
    )

    _precision_log("타이밍 재정렬 시작: VAD/단어 타임스탬프 기준")
    timed = refine_segment_edges_with_context(
        corrected,
        vad_segments=vad_segments,
        frame_rate=fps,
        max_word_shift_sec=0.18,
        max_vad_shift_sec=0.18,
        max_start_shift_sec=0.36,
        prefer_precision_vad_start=True,
    )
    _precision_log(f"타이밍 재정렬 완료: 자막 {len(timed)}개")
    _precision_debug("timing refine done", timed_count=len(timed), fps=fps, vad_count=len(vad_segments))

    _precision_status(status_callback, "불확실 구간 정밀 Whisper 확인 중...")
    _precision_log("선택 정밀 Whisper 확인 시작")
    precision_whisper = run_selective_precision_whisper(
        timed,
        media_path=media_path,
        audio_path=str(
            (lattice_result.audio_paths or {}).get("measured_audio_path")
            or (lattice_result.audio_paths or {}).get("raw_audio_path")
            or ""
        ),
        lattice_segments=vad_segments,
        settings=settings,
    )
    timed = [dict(seg) for seg in list(precision_whisper.segments or ())]
    whisper_report = dict(precision_whisper.report or {})
    _precision_log(
        "선택 정밀 Whisper 완료: "
        f"대상 {int(whisper_report.get('target_count', 0) or 0)}개 · "
        f"반영 {int(whisper_report.get('accepted_count', 0) or 0)}개"
    )
    _precision_debug("selective whisper done", report=whisper_report)

    _precision_status(status_callback, "정밀 자막자석 적용 중...")
    policy = compute_subtitle_magnet_policy(settings)
    threshold_sec = _safe_float(policy.get("continuous_threshold_sec"), 3.0)
    _precision_log(f"정밀 자막자석 적용 시작: threshold={threshold_sec:.2f}s")
    magneted, magnet_report = apply_netflix_subtitle_magnet(
        timed,
        threshold_sec=threshold_sec,
        boundary_times=boundary_times,
        provisional_boundaries=provisional_boundaries,
        vad_segments=vad_segments,
        speaker_strict=True,
        fps=fps,
        policy=policy,
    )
    final_segments = [dict(seg) for seg in list(magneted or []) if isinstance(seg, dict)]
    changed = _changed_count(before, final_segments)
    _precision_log(f"정밀 자막자석 완료: 자막 {len(final_segments)}개 · 변경 {changed}개")
    _precision_debug("magnet done", report=dict(magnet_report or {}), final_count=len(final_segments), changed_count=changed)

    report = {
        "before_count": len(before),
        "after_count": len(final_segments),
        "changed_count": changed,
        "vad_count": len(vad_segments),
        "boundary_count": len(boundary_times),
        "provisional_count": len(provisional_boundaries),
        "clip_boundary_count": len(clip_boundaries),
        "precision_vad_lattice": dict(lattice_result.report or {}),
        "precision_spellcheck": spellcheck_report,
        "selective_precision_whisper": whisper_report,
        "magnet": dict(magnet_report or {}),
        "quality_summary": quality_summary,
    }
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    _precision_log(
        "완료: "
        f"rows={len(before)} changed={changed} vad={len(vad_segments)} "
        f"boundaries={len(boundary_times)} provisional={len(provisional_boundaries)} "
        f"spellcheck={int(spellcheck_report.get('changed_count', 0) or 0)} "
        f"precision_whisper={int(whisper_report.get('accepted_count', 0) or 0)}/"
        f"{int(whisper_report.get('target_count', 0) or 0)} "
        f"magnet_closed={int((magnet_report or {}).get('closed_pairs', 0) or 0)}"
    )
    _precision_debug(
        "run complete",
        elapsed_ms=round(elapsed_ms, 1),
        changed_count=changed,
        vad_count=len(vad_segments),
        boundary_count=len(boundary_times),
        provisional_count=len(provisional_boundaries),
        spellcheck_report=spellcheck_report,
        whisper_report=whisper_report,
        magnet_report=dict(magnet_report or {}),
    )
    return {
        "before": before,
        "final_segments": final_segments,
        "changed_count": changed,
        "boundary_times": boundary_times,
        "provisional_boundaries": provisional_boundaries,
        "voice_activity_segments": vad_segments,
        "quality_summary": quality_summary,
        "report": report,
    }


class EditorPrecisionRefineMixin:
    def _precision_refine_available(self) -> bool:
        if bool(getattr(self, "_precision_refine_running", False)):
            return False
        if bool(getattr(self, "_is_ai_processing", False)):
            return False
        try:
            if str(getattr(getattr(self, "sm", None), "state", "") or "") == "ST_PROC":
                return False
        except Exception:
            return False
        getter = getattr(self, "_get_current_segments", None)
        if not callable(getter):
            return False
        try:
            segments = list(getter() or [])
        except Exception:
            return False
        return any(
            isinstance(seg, dict)
            and not bool(seg.get("is_gap"))
            and bool(str(seg.get("text", "") or "").strip())
            for seg in segments
        )

    def start_precision_subtitle_refinement(self) -> None:
        if not self._precision_refine_available():
            show_message(
                _precision_dialog_parent(self),
                "정밀 작업",
                "자막 생성 완료 후 사용할 수 있습니다.",
                icon=QMessageBox.Icon.Information,
            )
            return
        self._precision_refine_completed = False
        self._precision_refine_running = True
        try:
            job = self._precision_refine_job_snapshot()
        except Exception as exc:
            self._precision_refine_running = False
            _precision_log(f"시작 실패: {type(exc).__name__}: {exc}", level="ERROR")
            show_message(
                _precision_dialog_parent(self),
                "정밀 작업 오류",
                str(exc),
                icon=QMessageBox.Icon.Warning,
            )
            self._sync_precision_menu_state()
            return
        queued_segments = list(job.get("before") or [])
        if not queued_segments:
            self._precision_refine_running = False
            _precision_log("실행 취소: 정밀 작업을 실행할 자막이 없습니다.", level="WARN")
            show_message(
                _precision_dialog_parent(self),
                "정밀 작업",
                "정밀 작업을 실행할 자막이 없습니다.",
                icon=QMessageBox.Icon.Information,
            )
            self._sync_precision_menu_state()
            return
        _precision_log(
            f"시작 예약: 자막 {len(queued_segments)}개 · media={_precision_media_label(getattr(self, 'media_path', ''))}"
        )
        _precision_log(f"시작 확인: 정밀 작업 실행 준비 완료 · 자막 {len(queued_segments)}개")
        _precision_debug(
            "start scheduled",
            media_path=str(getattr(self, "media_path", "") or ""),
            fps=_safe_float(getattr(self, "video_fps", 30.0), 30.0),
            segment_count=len(queued_segments),
            setting_count=len(dict(getattr(self, "settings", {}) or {})),
        )
        if hasattr(self, "status_lbl"):
            self.status_lbl.setText("정밀 자막 작업 준비 중...")
        self._sync_precision_menu_state()
        self._start_precision_refine_worker(job)

    def _sync_precision_menu_state(self) -> None:
        try:
            main_w = self.window()
            sync_menu = getattr(main_w, "sync_menu_from_editor", None)
            if callable(sync_menu):
                sync_menu(self)
        except Exception:
            pass

    def _precision_canvas(self):
        timeline = getattr(self, "timeline", None)
        return getattr(timeline, "canvas", None) if timeline is not None else None

    def _precision_existing_vad_segments(self) -> list[dict[str, Any]]:
        canvas = self._precision_canvas()
        rows: list[dict[str, Any]] = []
        if canvas is None:
            return rows
        rows.extend(dict(row) for row in list(getattr(canvas, "vad_segments", []) or []) if isinstance(row, dict))
        return _merge_vad_rows(rows)

    def _precision_existing_voice_activity_segments(self) -> list[dict[str, Any]]:
        canvas = self._precision_canvas()
        rows: list[dict[str, Any]] = []
        if canvas is None:
            return rows
        for row in list(getattr(canvas, "voice_activity_segments", []) or []):
            if not isinstance(row, dict):
                continue
            kind = str(row.get("kind", row.get("source", "")) or "").strip().lower()
            label = str(row.get("label", "") or "").strip()
            if kind in {"idle", "silence", "gap", "non_speech"}:
                continue
            if label and label not in {"음성", "VAD", "speech"} and kind not in {"speech", "vad", "voice"}:
                continue
            rows.append(dict(row))
        return _merge_vad_rows(rows)

    def _precision_vad_segments(self) -> list[dict[str, Any]]:
        return _merge_vad_rows(self._precision_existing_vad_segments() + self._precision_existing_voice_activity_segments())

    def _precision_audio_paths(self) -> dict[str, Any]:
        paths: dict[str, Any] = {}
        processors = []
        try:
            window = self.window()
        except Exception:
            window = None
        for owner in (
            getattr(getattr(window, "backend", None), "video_processor", None),
            getattr(window, "video_processor", None),
            getattr(self, "video_processor", None),
        ):
            if owner is not None and owner not in processors:
                processors.append(owner)
        for processor in processors:
            cleaned = str(getattr(processor, "last_cleaned_wav", "") or "")
            raw = str(getattr(processor, "last_raw_wav", "") or "")
            if cleaned:
                paths.setdefault("measured_audio_path", cleaned)
            if raw:
                paths.setdefault("raw_audio_path", raw)
            last_audio_paths = getattr(processor, "last_audio_paths", None)
            if isinstance(last_audio_paths, dict):
                paths.setdefault("cleaned_wav", last_audio_paths.get("cleaned_wav"))
                paths.setdefault("raw_wav", last_audio_paths.get("raw_wav"))
                paths.setdefault("work_dir", last_audio_paths.get("work_dir"))
        return paths

    def _precision_video_processor(self):
        try:
            window = self.window()
        except Exception:
            window = None
        for owner in (
            getattr(getattr(window, "backend", None), "video_processor", None),
            getattr(window, "video_processor", None),
            getattr(self, "video_processor", None),
        ):
            if owner is not None:
                return owner
        return None

    def _precision_boundary_times(self) -> list[Any]:
        canvas = self._precision_canvas()
        if canvas is None:
            return []
        boundaries = list(getattr(canvas, "boundary_times", []) or [])
        marker_getter = getattr(canvas, "roughcut_major_markers_cached", None)
        if callable(marker_getter):
            try:
                for marker in list(marker_getter() or []):
                    if not isinstance(marker, dict):
                        continue
                    if marker.get("start") is not None:
                        boundaries.append(marker.get("start"))
                    if marker.get("end") is not None:
                        boundaries.append(marker.get("end"))
            except Exception:
                pass
        return boundaries

    def _precision_provisional_boundaries(self) -> list[Any]:
        canvas = self._precision_canvas()
        if canvas is None:
            return []
        return list(getattr(canvas, "scan_boundary_times", []) or [])

    def _precision_refine_job_snapshot(self) -> dict[str, Any]:
        before = [
            dict(seg)
            for seg in list(self._get_current_segments(force_rebuild=True) or [])
            if isinstance(seg, dict) and not bool(seg.get("is_gap"))
        ]
        dialog_parent = _precision_dialog_parent(self)
        return {
            "before": before,
            "media_path": str(getattr(self, "media_path", "") or ""),
            "fps": _safe_float(getattr(self, "video_fps", 30.0), 30.0),
            "existing_vad_segments": self._precision_existing_vad_segments(),
            "existing_voice_activity_segments": self._precision_existing_voice_activity_segments(),
            "boundary_times": self._precision_boundary_times(),
            "provisional_boundaries": self._precision_provisional_boundaries(),
            "clip_boundaries": _precision_clip_boundaries(getattr(dialog_parent, "_multiclip_boundaries", None)),
            "audio_paths": self._precision_audio_paths(),
            "video_processor": self._precision_video_processor(),
            "settings": dict(getattr(self, "settings", {}) or {}),
        }

    def _start_precision_refine_worker(self, job: dict[str, Any]) -> None:
        token = object()
        self._precision_refine_token = token
        bridge_parent = self if isinstance(self, QObject) else None
        bridge = _PrecisionRefineBridge(bridge_parent)
        self._precision_refine_bridge = bridge
        bridge.progress.connect(lambda text, token=token: self._on_precision_refine_progress(token, text))
        bridge.succeeded.connect(lambda result, token=token: self._on_precision_refine_succeeded(token, result))
        bridge.failed.connect(lambda payload, token=token: self._on_precision_refine_failed(token, payload))

        def _emit_progress(text: str) -> None:
            try:
                bridge.progress.emit(str(text or ""))
            except RuntimeError:
                pass

        def _worker() -> None:
            started_at = time.perf_counter()
            try:
                result = _precision_compute_refinement_job(job, status_callback=_emit_progress)
            except Exception as exc:
                _precision_log_failure(
                    exc,
                    started_at=started_at,
                    before_count=len(list(job.get("before") or [])),
                    final_count=0,
                )
                try:
                    bridge.failed.emit({"type": type(exc).__name__, "message": str(exc)})
                except RuntimeError:
                    pass
                return
            try:
                bridge.succeeded.emit(result)
            except RuntimeError:
                pass

        thread = threading.Thread(target=_worker, daemon=True, name="precision-subtitle-refine")
        self._precision_refine_thread = thread
        try:
            thread.start()
        except Exception as exc:
            self._precision_refine_running = False
            self._precision_refine_token = None
            self._precision_refine_thread = None
            self._precision_refine_bridge = None
            _precision_log(f"스레드 시작 실패: {type(exc).__name__}: {exc}", level="ERROR")
            show_message(
                _precision_dialog_parent(self),
                "정밀 작업 오류",
                str(exc),
                icon=QMessageBox.Icon.Warning,
            )
            self._sync_precision_menu_state()

    def _on_precision_refine_progress(self, token: object, text: str) -> None:
        if getattr(self, "_precision_refine_token", None) is not token:
            return
        if hasattr(self, "status_lbl"):
            self.status_lbl.setText(str(text or "정밀 자막 작업 진행 중..."))

    def _finish_precision_refine_worker(self, token: object) -> bool:
        if getattr(self, "_precision_refine_token", None) is not token:
            return False
        self._precision_refine_running = False
        self._precision_refine_token = None
        self._precision_refine_thread = None
        self._precision_refine_bridge = None
        self._sync_precision_menu_state()
        return True

    def _apply_precision_refine_result(self, result: dict[str, Any]) -> None:
        before = [dict(seg) for seg in list(result.get("before") or []) if isinstance(seg, dict)]
        final_segments = [dict(seg) for seg in list(result.get("final_segments") or []) if isinstance(seg, dict)]
        changed = int(result.get("changed_count", _changed_count(before, final_segments)) or 0)
        boundary_times = list(result.get("boundary_times") or [])
        provisional_boundaries = list(result.get("provisional_boundaries") or [])
        voice_activity_segments = [
            dict(row) for row in list(result.get("voice_activity_segments") or []) if isinstance(row, dict)
        ]
        self._last_precision_refine_report = dict(result.get("report") or {})
        if changed > 0 and hasattr(self, "_undo_mgr"):
            self._undo_mgr.push_immediate()
        if hasattr(self, "apply_loaded_canvas_state"):
            self.apply_loaded_canvas_state(
                final_segments,
                preserve_view=True,
                mark_dirty=False,
                boundary_times=boundary_times,
                provisional_boundaries=provisional_boundaries,
                voice_activity_segments=voice_activity_segments,
            )
        self._quality_summary = result.get("quality_summary")
        updater = getattr(self, "_update_quality_summary_label", None)
        if callable(updater):
            updater()
        if changed > 0:
            self._autosave_requires_manual_save = True
            if hasattr(self, "_mark_dirty"):
                self._mark_dirty()
        if hasattr(self, "_schedule_timeline"):
            self._schedule_timeline()
        if hasattr(self, "_refresh_video_subtitle_context"):
            self._refresh_video_subtitle_context()
        if hasattr(self, "status_lbl"):
            if changed > 0:
                self.status_lbl.setText(f"정밀 자막 작업 완료 · {changed}개 조정 · 수동 저장 필요")
            else:
                self.status_lbl.setText("정밀 자막 작업 완료 · 조정 없음")
        self._precision_refine_completed = True

    def _on_precision_refine_succeeded(self, token: object, result: object) -> None:
        if getattr(self, "_precision_refine_token", None) is not token:
            return
        apply_error: BaseException | None = None
        try:
            _precision_log("UI 반영 시작: 정밀 자막 결과 적용")
            self._apply_precision_refine_result(dict(result or {}))
            _precision_log("UI 반영 완료: 정밀 자막 결과 적용")
            applied = dict(result or {})
            changed = int(applied.get("changed_count", 0) or 0)
            _precision_log(f"정밀 작업 완료: 에디터 반영 완료 · 변경 {changed}개")
        except Exception as exc:
            apply_error = exc
            _precision_log(f"UI 반영 실패: {type(exc).__name__}: {exc}", level="ERROR")
            _precision_debug("apply result failed", error_type=type(exc).__name__, error=str(exc))
        finally:
            self._finish_precision_refine_worker(token)
        if apply_error is not None:
            if hasattr(self, "status_lbl"):
                self.status_lbl.setText("정밀 자막 작업 실패")
            show_message(
                _precision_dialog_parent(self),
                "정밀 작업 오류",
                str(apply_error),
                icon=QMessageBox.Icon.Warning,
            )

    def _on_precision_refine_failed(self, token: object, payload: object) -> None:
        if not self._finish_precision_refine_worker(token):
            return
        data = dict(payload or {}) if isinstance(payload, dict) else {"message": str(payload or "")}
        message = str(data.get("message") or "정밀 자막 작업을 완료하지 못했습니다.")
        _precision_log(f"정밀 작업 실패: {message}", level="ERROR")
        self._precision_refine_completed = False
        if hasattr(self, "status_lbl"):
            self.status_lbl.setText("정밀 자막 작업 실패")
        show_message(
            _precision_dialog_parent(self),
            "정밀 작업 오류",
            message,
            icon=QMessageBox.Icon.Warning,
        )

    def _run_precision_subtitle_refinement(self) -> None:
        started_at = time.perf_counter()
        before_count = 0
        final_count = 0
        self._precision_refine_completed = False
        try:
            job = self._precision_refine_job_snapshot()
            before_count = len(list(job.get("before") or []))
            if not before_count:
                _precision_log("실행 취소: 정밀 작업을 실행할 자막이 없습니다.", level="WARN")
                _precision_debug("cancelled: no subtitle segments")
                show_message(
                    _precision_dialog_parent(self),
                    "정밀 작업",
                    "정밀 작업을 실행할 자막이 없습니다.",
                    icon=QMessageBox.Icon.Information,
                )
                return
            result = _precision_compute_refinement_job(
                job,
                status_callback=(
                    (lambda text: self.status_lbl.setText(text))
                    if hasattr(self, "status_lbl")
                    else None
                ),
            )
            final_count = len(list(result.get("final_segments") or []))
            _precision_log("UI 반영 시작: 정밀 자막 결과 적용")
            self._apply_precision_refine_result(result)
            _precision_log("UI 반영 완료: 정밀 자막 결과 적용")
            _precision_log(f"정밀 작업 완료: 에디터 반영 완료 · 변경 {int(result.get('changed_count', 0) or 0)}개")
        except Exception as exc:
            _precision_log_failure(
                exc,
                started_at=started_at,
                before_count=before_count,
                final_count=final_count,
            )
            show_message(
                _precision_dialog_parent(self),
                "정밀 작업 오류",
                str(exc),
                icon=QMessageBox.Icon.Warning,
            )
        finally:
            self._precision_refine_running = False
            self._sync_precision_menu_state()
