from __future__ import annotations

import os
import threading
import time
from typing import Any

BACKGROUND_PREFETCH_SCHEMA = "ai_subtitle_studio.background_prefetch.v1"


def _safe_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "n", "끔", "아니오"}
    return bool(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return int(default)
        return int(round(float(value)))
    except Exception:
        return int(default)


def _segment_window(segments: list[dict[str, Any]], current_sec: float, before_sec: float, after_sec: float, limit: int) -> list[dict[str, Any]]:
    start = max(0.0, float(current_sec or 0.0) - max(0.0, before_sec))
    end = float(current_sec or 0.0) + max(0.0, after_sec)
    rows = []
    for row in list(segments or []):
        if not isinstance(row, dict) or row.get("is_gap"):
            continue
        seg_start = _safe_float(row.get("start", row.get("timeline_start")), 0.0)
        seg_end = _safe_float(row.get("end", row.get("timeline_end")), seg_start)
        if seg_end >= start and seg_start <= end:
            rows.append(dict(row))
    rows.sort(key=lambda item: (abs((_safe_float(item.get("start"), 0.0) + _safe_float(item.get("end"), 0.0)) / 2.0 - current_sec), _safe_float(item.get("start"), 0.0)))
    return rows[: max(1, int(limit or 1))]


def build_background_prefetch_plan(
    *,
    media_path: str = "",
    current_sec: float = 0.0,
    segments: list[dict[str, Any]] | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = dict(settings or {})
    enabled = _safe_bool(settings.get("background_prefetch_enabled"), True)
    before_sec = _safe_float(settings.get("background_prefetch_before_sec"), 18.0)
    after_sec = _safe_float(settings.get("background_prefetch_after_sec"), 72.0)
    segment_limit = _safe_int(settings.get("background_prefetch_segment_limit"), 10)
    lora_limit = _safe_int(settings.get("background_prefetch_lora_limit"), 4)
    candidate_limit = _safe_int(settings.get("background_prefetch_candidate_limit"), 8)
    nearby = _segment_window(list(segments or []), float(current_sec or 0.0), before_sec, after_sec, segment_limit)
    return {
        "schema": BACKGROUND_PREFETCH_SCHEMA,
        "enabled": enabled,
        "media_path": os.path.abspath(str(media_path or "")) if media_path else "",
        "current_sec": round(float(current_sec or 0.0), 3),
        "window": {
            "start": round(max(0.0, float(current_sec or 0.0) - before_sec), 3),
            "end": round(float(current_sec or 0.0) + after_sec, 3),
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
        self.last_result: dict[str, Any] = {}

    def request(
        self,
        *,
        media_path: str = "",
        current_sec: float = 0.0,
        segments: list[dict[str, Any]] | None = None,
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
            self._last_key = key
            self._last_request_mono = now
            self._thread = threading.Thread(
                target=self._run_prefetch,
                args=(plan, settings),
                daemon=True,
                name="background-prefetch",
            )
            self._thread.start()
        return {**plan, "queued": True, "reason": "started"}

    def _run_prefetch(self, plan: dict[str, Any], settings: dict[str, Any]) -> None:
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

            segments = list(plan.get("segments") or [])
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
            self.last_result = result


__all__ = [
    "BACKGROUND_PREFETCH_SCHEMA",
    "BackgroundPrefetchManager",
    "build_background_prefetch_plan",
]
