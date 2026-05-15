from __future__ import annotations

import os
import threading
import time
from heapq import nsmallest
from typing import Any

from core.coerce import safe_float as _safe_float, safe_round_int as _safe_int
from core.runtime.setting_utils import setting_bool as _setting_bool

BACKGROUND_PREFETCH_SCHEMA = "ai_subtitle_studio.background_prefetch.v1"
_PREFETCH_SEGMENT_KEYS = (
    "start",
    "end",
    "timeline_start",
    "timeline_end",
    "text",
    "source",
    "stt_source",
    "stt_ensemble_source",
    "stt_selected_source",
    "label",
    "speaker",
    "spk",
)
_PREFETCH_CANDIDATE_KEYS = (
    "stt_candidates",
    "stt_lattice_candidates",
    "vad_candidates",
    "stt_retry_candidates",
    "stt_recheck_candidates",
    "stt_rescue_candidates",
    "manual_stt_candidates",
    "manual_recheck_candidates",
    "manual_rerecognition_candidates",
    "manual_re_recognition_candidates",
    "stt_manual_candidates",
)


def _safe_bool(value: Any, default: bool = False) -> bool:
    return _setting_bool(
        value,
        default,
        false_values={"0", "false", "off", "no", "n", "끔", "아니오"},
        false_only_strings=True,
        empty_is_default=False,
    )

def _prefetch_segment_bounds(row: dict[str, Any]) -> tuple[float, float]:
    seg_start = _safe_float(row.get("start", row.get("timeline_start")), 0.0)
    seg_end = _safe_float(row.get("end", row.get("timeline_end")), seg_start)
    return seg_start, max(seg_start, seg_end)


def _project_prefetch_segment(row: dict[str, Any], seg_start: float, seg_end: float) -> dict[str, Any]:
    projected = {
        "start": seg_start,
        "end": seg_end,
        "timeline_start": _safe_float(row.get("timeline_start"), seg_start),
        "timeline_end": _safe_float(row.get("timeline_end"), seg_end),
        "text": str(row.get("text") or ""),
    }
    for key in _PREFETCH_SEGMENT_KEYS[5:]:
        if key in row:
            projected[key] = row.get(key)
    for key in _PREFETCH_CANDIDATE_KEYS:
        if key in row:
            projected[key] = row.get(key)
    return projected


def _segment_window(segments, current_sec: float, before_sec: float, after_sec: float, limit: int) -> list[dict[str, Any]]:
    start = max(0.0, float(current_sec or 0.0) - max(0.0, before_sec))
    end = float(current_sec or 0.0) + max(0.0, after_sec)
    rows = []
    for row in segments or ():
        if not isinstance(row, dict) or row.get("is_gap"):
            continue
        seg_start, seg_end = _prefetch_segment_bounds(row)
        if seg_end >= start and seg_start <= end:
            projected = _project_prefetch_segment(row, seg_start, seg_end)
            rows.append((abs((seg_start + seg_end) / 2.0 - current_sec), seg_start, projected))
    limited = nsmallest(max(1, int(limit or 1)), rows)
    return [row for _dist, _start, row in limited]


def build_background_prefetch_plan(
    *,
    media_path: str = "",
    current_sec: float = 0.0,
    segments=None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = dict(settings or {})
    enabled = _safe_bool(settings.get("background_prefetch_enabled"), True)
    before_sec = _safe_float(settings.get("background_prefetch_before_sec"), 18.0)
    after_sec = _safe_float(settings.get("background_prefetch_after_sec"), 72.0)
    segment_limit = _safe_int(settings.get("background_prefetch_segment_limit"), 10)
    lora_limit = _safe_int(settings.get("background_prefetch_lora_limit"), 4)
    candidate_limit = _safe_int(settings.get("background_prefetch_candidate_limit"), 8)
    current = float(current_sec or 0.0)
    nearby = _segment_window(segments, current, before_sec, after_sec, segment_limit)
    return {
        "schema": BACKGROUND_PREFETCH_SCHEMA,
        "enabled": enabled,
        "media_path": os.path.abspath(str(media_path or "")) if media_path else "",
        "current_sec": round(current, 3),
        "window": {
            "start": round(max(0.0, current - before_sec), 3),
            "end": round(current + after_sec, 3),
            "before_sec": before_sec,
            "after_sec": after_sec,
        },
        "segment_count": len(nearby),
        "segments": nearby,
        "lora_limit": max(0, lora_limit),
        "candidate_limit": max(0, candidate_limit),
        "waveform": {"requested": bool(media_path), "cache_checked": False, "cache_hit": False, "path": ""},
    }


class BackgroundPrefetchManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._last_key = ""
        self._last_request_mono = 0.0
        self._generation = 0
        self.last_result: dict[str, Any] = {}

    def request(
        self,
        *,
        media_path: str = "",
        current_sec: float = 0.0,
        segments=None,
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        settings = dict(settings or {})
        plan = build_background_prefetch_plan(
            media_path=media_path,
            current_sec=current_sec,
            segments=segments,
            settings=settings,
        )
        if not plan.get("enabled"):
            return {**plan, "queued": False, "reason": "disabled"}
        if not plan.get("segment_count") and not media_path:
            return {**plan, "queued": False, "reason": "empty"}

        bucket_sec = max(1.0, _safe_float(settings.get("background_prefetch_bucket_sec"), 6.0))
        key = f"{os.path.abspath(str(media_path or ''))}|{int(float(current_sec or 0.0) // bucket_sec)}"
        now = time.monotonic()
        min_interval = max(0.1, _safe_float(settings.get("background_prefetch_min_interval_sec"), 0.75))
        with self._lock:
            if key == self._last_key and (now - self._last_request_mono) < min_interval:
                return {**plan, "queued": False, "reason": "throttled"}
            if self._thread is not None and self._thread.is_alive():
                return {**plan, "queued": False, "reason": "busy"}
            generation = int(self._generation)
            self._last_key = key
            self._last_request_mono = now
            self._thread = threading.Thread(
                target=self._run_prefetch,
                args=(generation, plan, settings),
                daemon=True,
                name="background-prefetch",
            )
            self._thread.start()
        return {**plan, "queued": True, "reason": "started"}

    def clear(self) -> None:
        with self._lock:
            self._generation += 1
            self._last_key = ""
            self._last_request_mono = 0.0
            self.last_result = {}
            if self._thread is not None and not self._thread.is_alive():
                self._thread = None

    def _run_prefetch(self, generation: int, plan: dict[str, Any], settings: dict[str, Any]) -> None:
        result = dict(plan)
        lora_results = []
        candidate_results = []
        try:
            media_path = str(plan.get("media_path") or "")
            if media_path:
                try:
                    from ui.timeline.timeline_waveform import load_waveform_cache, waveform_cache_path

                    cache_path = waveform_cache_path(media_path)
                    cached = load_waveform_cache(media_path)
                    result["waveform"] = {
                        "requested": True,
                        "cache_checked": True,
                        "cache_hit": cached is not None,
                        "path": cache_path,
                    }
                except Exception:
                    result["waveform"] = {"requested": True, "cache_checked": False, "cache_hit": False, "path": ""}

            segments = plan.get("segments") or ()
            if plan.get("lora_limit", 0) > 0 and _safe_bool(settings.get("background_prefetch_lora_enabled"), True):
                from core.personalization.lora_vector_retriever import retrieve_lora_context

                for row in segments[: int(plan.get("lora_limit") or 0)]:
                    text = str(row.get("text") or "").strip()
                    if not text:
                        continue
                    lora_results.append(
                        retrieve_lora_context(
                            text,
                            media_path=media_path,
                            settings=settings,
                            context={"prefetch": True, "current_sec": plan.get("current_sec")},
                            limit=max(1, min(8, _safe_int(settings.get("background_prefetch_lora_retrieval_limit"), 4))),
                            per_kind=2,
                            rebuild_if_stale=False,
                        )
                    )

            if plan.get("candidate_limit", 0) > 0 and _safe_bool(settings.get("background_prefetch_candidates_enabled"), True):
                from core.audio.stt_lattice import collect_stt_lattice_candidates

                for row in segments[: int(plan.get("candidate_limit") or 0)]:
                    candidate_results.append(
                        {
                            "start": row.get("start"),
                            "end": row.get("end"),
                            "candidate_count": len(collect_stt_lattice_candidates(row, include_current=True, limit=16)),
                        }
                    )
        except Exception as exc:
            result["error"] = str(exc)
        result["lora_prefetch_count"] = len(lora_results)
        result["candidate_prefetch_count"] = len(candidate_results)
        result["completed_at_mono"] = round(time.monotonic(), 3)
        with self._lock:
            if int(generation) == int(self._generation):
                self.last_result = result


__all__ = [
    "BACKGROUND_PREFETCH_SCHEMA",
    "BackgroundPrefetchManager",
    "build_background_prefetch_plan",
]
