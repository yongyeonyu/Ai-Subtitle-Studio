# Version: 03.11.16
# Phase: PHASE2
"""Cut-boundary helpers for absolute scene splits."""
from __future__ import annotations

from copy import deepcopy
import os
from typing import Any

from core.frame_time import frame_to_sec, normalize_fps, sec_to_frame
from core.media_info import probe_media

CUT_BOUNDARY_SCHEMA = "cut_boundaries.v1"
CUT_SEGMENT_SCHEMA = "cut_boundary_segments.v1"
MIN_SLICE_SEC = 0.02


def cut_boundary_enabled(settings: dict[str, Any] | None) -> bool:
    settings = settings or {}
    return bool(settings.get("cut_boundary_detection_enabled", settings.get("scan_cut_enabled", True)))


def normalize_cut_boundaries(
    boundaries: list[dict[str, Any]] | None,
    *,
    primary_fps: float = 30.0,
) -> list[dict[str, Any]]:
    fps = normalize_fps(primary_fps or 30.0)
    out: list[dict[str, Any]] = []
    seen_frames: set[int] = set()
    for idx, item in enumerate(boundaries or []):
        if not isinstance(item, dict):
            continue
        try:
            sec = float(
                item.get("timeline_sec", item.get("time", item.get("start", item.get("timeline_start", 0.0))))
                or 0.0
            )
        except Exception:
            continue
        frame = item.get("timeline_frame", item.get("frame"))
        try:
            frame = int(frame) if frame is not None else sec_to_frame(sec, fps)
        except Exception:
            frame = sec_to_frame(sec, fps)
        sec = frame_to_sec(frame, fps)
        if sec <= 0.0 or frame in seen_frames:
            continue
        seen_frames.add(frame)
        row = dict(item)
        row.update(
            {
                "schema": "cut_boundary.v1",
                "id": str(row.get("id") or f"cut_{frame:08d}"),
                "time": sec,
                "timeline_sec": sec,
                "frame": frame,
                "timeline_frame": frame,
                "fps": fps,
                "absolute": True,
                "locked": True,
                "source": str(row.get("source") or "visual"),
            }
        )
        row.setdefault("detector", "opencv-gray-pyramid60")
        row.setdefault("reason", "visual_cut_boundary")
        row.setdefault("index", idx + 1)
        out.append(row)
    out.sort(key=lambda item: (float(item.get("timeline_sec", 0.0) or 0.0), int(item.get("timeline_frame", 0) or 0)))
    for idx, item in enumerate(out, start=1):
        item["index"] = idx
    return out


def project_cut_boundaries(project: dict[str, Any] | None, *, primary_fps: float | None = None) -> list[dict[str, Any]]:
    if not isinstance(project, dict):
        return []
    if primary_fps is None:
        timebase = (project.get("timeline", {}) or {}).get("timebase", {}) or project.get("frame_timebase", {}) or {}
        primary_fps = timebase.get("primary_fps", 30.0)
    analysis = project.get("analysis", {}) or {}
    raw = analysis.get("cut_boundaries")
    if not isinstance(raw, list):
        raw = ((project.get("editor_state", {}) or {}).get("multiclip", {}) or {}).get("cut_boundaries")
    if not isinstance(raw, list):
        raw = []
    return normalize_cut_boundaries(raw, primary_fps=normalize_fps(primary_fps or 30.0))


def sync_project_cut_boundaries(
    project: dict[str, Any],
    *,
    settings: dict[str, Any] | None = None,
    primary_fps: float = 30.0,
) -> list[dict[str, Any]]:
    boundaries = project_cut_boundaries(project, primary_fps=primary_fps)
    analysis = project.setdefault("analysis", {})
    analysis["cut_boundary_schema"] = CUT_BOUNDARY_SCHEMA
    analysis["cut_boundaries"] = boundaries
    analysis["cut_boundary_settings"] = {
        "enabled": cut_boundary_enabled(settings if settings is not None else project.get("user_settings")),
        "detector": "opencv-gray-pyramid60",
        "count": len(boundaries),
        "absolute": True,
        "locked": True,
    }
    editor_state = project.get("editor_state")
    if isinstance(editor_state, dict):
        editor_state.setdefault("analysis", {})
        editor_state["analysis"]["cut_boundary_schema"] = CUT_BOUNDARY_SCHEMA
        editor_state["analysis"]["cut_boundaries"] = list(boundaries)
        multiclip = editor_state.setdefault("multiclip", {})
        multiclip["cut_boundary_schema"] = CUT_BOUNDARY_SCHEMA
        multiclip["cut_boundaries"] = list(boundaries)
    return boundaries


def split_segments_by_cut_boundaries(
    segments: list[dict[str, Any]] | None,
    boundaries: list[dict[str, Any]] | None,
    *,
    enabled: bool = True,
    primary_fps: float = 30.0,
) -> list[dict[str, Any]]:
    if not segments:
        return []
    if not enabled:
        return [dict(seg) for seg in segments if isinstance(seg, dict)]

    cuts = normalize_cut_boundaries(boundaries, primary_fps=primary_fps)
    cut_times = [float(item.get("timeline_sec", item.get("time", 0.0)) or 0.0) for item in cuts]
    if not cut_times:
        return [dict(seg) for seg in segments if isinstance(seg, dict)]

    out: list[dict[str, Any]] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        item = _fit_one_segment_to_cut(seg, cut_times, cuts, primary_fps=primary_fps)
        if item is not None:
            out.append(item)
    for idx, item in enumerate(out):
        item["line"] = idx
        item["index"] = idx + 1
    return out


def _fit_one_segment_to_cut(
    seg: dict[str, Any],
    cut_times: list[float],
    cuts: list[dict[str, Any]],
    *,
    primary_fps: float,
) -> dict[str, Any] | None:
    start = _as_float(seg.get("start", seg.get("timeline_start", 0.0)))
    end = _as_float(seg.get("end", seg.get("timeline_end", start)), start)
    end = max(start, end)
    if end <= start + MIN_SLICE_SEC:
        row = dict(seg)
        _attach_cut_local_fields(row, cut_times, cuts, primary_fps=primary_fps)
        return row

    midpoint = (start + end) / 2.0
    scene_start = 0.0
    scene_end: float | None = None
    scene_index = 0
    for idx, cut in enumerate(cut_times):
        if cut <= midpoint:
            scene_start = cut
            scene_index = idx + 1
        elif cut > midpoint:
            scene_end = cut
            break
    fitted_start = max(start, scene_start)
    fitted_end = end if scene_end is None else min(end, scene_end)
    if fitted_end <= fitted_start + MIN_SLICE_SEC:
        fitted_start = scene_start
        fitted_end = scene_end if scene_end is not None else max(end, scene_start + MIN_SLICE_SEC)
    if fitted_end <= fitted_start + MIN_SLICE_SEC:
        return None

    row = deepcopy(seg)
    row["start"] = fitted_start
    row["end"] = fitted_end
    row["timeline_start"] = fitted_start
    row["timeline_end"] = fitted_end
    row["start_frame"] = sec_to_frame(fitted_start, primary_fps)
    row["end_frame"] = sec_to_frame(fitted_end, primary_fps)
    row["timeline_start_frame"] = row["start_frame"]
    row["timeline_end_frame"] = row["end_frame"]
    row["frame_rate"] = primary_fps
    row["timeline_frame_rate"] = primary_fps
    row["frame_range"] = {
        "unit": "frame",
        "start": row["start_frame"],
        "end": row["end_frame"],
        "timeline_frame_rate": primary_fps,
    }
    row["cut_boundary_fitted"] = bool(fitted_start != start or fitted_end != end)
    row["words"] = _clip_timed_items(seg.get("words"), fitted_start, fitted_end)
    if "stt_candidates" in row:
        row["stt_candidates"] = _fit_candidates_to_interval(row.get("stt_candidates"), fitted_start, fitted_end, primary_fps)
    _attach_cut_local_fields(row, cut_times, cuts, primary_fps=primary_fps)
    row["cut_scene_index"] = scene_index
    row["cut_scene_start"] = scene_start
    if scene_end is not None:
        row["cut_scene_end"] = scene_end
    return row


def _fit_candidates_to_interval(candidates: Any, start: float, end: float, primary_fps: float) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(candidates, list):
        return out
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        c_start = _as_float(candidate.get("start", start), start)
        c_end = _as_float(candidate.get("end", end), end)
        overlap_start = max(start, c_start)
        overlap_end = min(end, c_end)
        if overlap_end <= overlap_start + MIN_SLICE_SEC:
            continue
        row = deepcopy(candidate)
        row["start"] = overlap_start
        row["end"] = overlap_end
        row["start_frame"] = sec_to_frame(overlap_start, primary_fps)
        row["end_frame"] = sec_to_frame(overlap_end, primary_fps)
        row["timeline_start_frame"] = row["start_frame"]
        row["timeline_end_frame"] = row["end_frame"]
        row["words"] = _clip_timed_items(candidate.get("words"), overlap_start, overlap_end)
        out.append(row)
    return out


def _clip_timed_items(items: Any, start: float, end: float) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    clipped: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        w_start = _as_float(item.get("start", start), start)
        w_end = _as_float(item.get("end", w_start), w_start)
        if max(start, w_start) < min(end, w_end):
            clipped.append(dict(item))
    return clipped


def _attach_cut_local_fields(
    row: dict[str, Any],
    cut_times: list[float],
    cuts: list[dict[str, Any]],
    *,
    primary_fps: float,
) -> None:
    start = _as_float(row.get("start", row.get("timeline_start", 0.0)))
    end = _as_float(row.get("end", row.get("timeline_end", start)), start)
    prev_cut = 0.0
    next_cut = None
    cut_index = 0
    for idx, cut in enumerate(cut_times):
        if cut <= start + MIN_SLICE_SEC:
            prev_cut = cut
            cut_index = idx + 1
        elif cut > start + MIN_SLICE_SEC:
            next_cut = cut
            break
    row["cut_boundary_schema"] = CUT_SEGMENT_SCHEMA
    row["cut_scene_index"] = cut_index
    row["cut_scene_start"] = prev_cut
    if next_cut is not None:
        row["cut_scene_end"] = next_cut
    row["cut_local_start"] = max(0.0, start - prev_cut)
    row["cut_local_end"] = max(row["cut_local_start"], end - prev_cut)
    row["cut_local_start_frame"] = sec_to_frame(row["cut_local_start"], primary_fps)
    row["cut_local_end_frame"] = sec_to_frame(row["cut_local_end"], primary_fps)
    if 0 <= cut_index < len(cuts):
        row["cut_boundary_prev_id"] = str(cuts[cut_index - 1].get("id", "")) if cut_index > 0 else ""
        row["cut_boundary_next_id"] = str(cuts[cut_index].get("id", "")) if cut_index < len(cuts) else ""


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "CUT_BOUNDARY_SCHEMA",
    "CUT_SEGMENT_SCHEMA",
    "cut_boundary_enabled",
    "detect_media_cut_boundaries",
    "normalize_cut_boundaries",
    "project_cut_boundaries",
    "split_segments_by_cut_boundaries",
    "sync_project_cut_boundaries",
]


def _legacy_detect_media_cut_boundaries(
    filepath: str,
    *,
    clip_offset: float = 0.0,
    clip_idx: int = 0,
    sample_step_sec: float = 1.0,
    threshold: float = 18.0,
    progress_callback=None,
    found_callback=None,
) -> list[dict[str, Any]]:
    """Scan one media file and return absolute cut-boundary rows."""
    try:
        info = probe_media(filepath)
        duration = float(info.get("duration", 0.0) or 0.0)
        fps = normalize_fps(info.get("fps", 30.0) or 30.0)
    except Exception:
        duration = 0.0
        fps = 30.0
    if duration <= 0.0:
        return []

    step = max(0.25, float(sample_step_sec or 1.0))
    rows: list[dict[str, Any]] = []
    last_progress_pct = -1
    estimated_steps = max(1, int(duration / step) + 1)

    def _report_progress(timestamp: float, *, force: bool = False):
        nonlocal last_progress_pct
        if not callable(progress_callback) or duration <= 0.0:
            return
        pct = int(min(100.0, max(0.0, (float(timestamp or 0.0) / duration) * 100.0)))
        if not force and pct < 100:
            pct = (pct // 10) * 10
        if pct <= last_progress_pct:
            return
        last_progress_pct = pct
        try:
            progress_callback(
                {
                    "clip_idx": int(clip_idx),
                    "percent": pct,
                    "timestamp": float(timestamp or 0.0),
                    "duration": duration,
                    "detected": len(rows),
                    "estimated_steps": estimated_steps,
                    "sample_step_sec": step,
                }
            )
        except Exception:
            pass

    try:
        from ui.editor.editor_timeline_video import (
            _rel_capture_image_at_global,
            _rel_image_delta,
            _rel_is_candidate,
            _rel_refine_boundary,
            _rel_scan_backend_label,
            _rel_scan_coarse_stride_frames,
        )
    except Exception:
        return []

    class _AutoScanAdapter:
        def __init__(self, source_path: str, fps_value: float, settings_obj: dict):
            self.settings = dict(settings_obj or {})
            self._source_path = str(source_path)
            self._fps = float(fps_value or 30.0)
            self._scan_cv2_mod = None
            self._scan_cv2_capture = None
            self._scan_cv2_source_path = None
            self._scan_logged_relative_resolution = False
            self._scan_last_region_deltas = []
            self._scan_last_region_hits = 0

            class _VideoPlayer:
                def __init__(self, path: str):
                    self._current_source_path = path

            self.video_player = _VideoPlayer(self._source_path)

        def _current_frame_fps(self) -> float:
            return float(self._fps)

        def _resolve_active_context(self, global_sec: float = 0.0):
            sec = max(0.0, float(global_sec or 0.0))
            return {
                "global_sec": sec,
                "local_sec": sec,
                "clip_file": self._source_path,
                "source_path": self._source_path,
            }

    adapter = _AutoScanAdapter(
        filepath,
        fps,
        {
            "scan_cut_threshold": float(threshold or 18.0),
            "scan_cut_region_threshold": float(threshold or 18.0),
            "scan_cut_relative_stride_frames": max(3, int(round(step * fps))),
        },
    )

    try:
        _report_progress(0.0, force=True)
        stride = max(1, int(_rel_scan_coarse_stride_frames(adapter)))
        total_frames = max(1, int(round(duration * fps)))
        last_frame = 0
        previous_score = 0.0
        baseline = 0.0
        resume_skip_frames = max(1, int(round(1.5 * fps)))

        while last_frame < total_frames:
            next_frame = min(total_frames, last_frame + stride)
            last_sec = last_frame / fps
            next_sec = next_frame / fps

            img_a = _rel_capture_image_at_global(adapter, last_sec, region_mode="fast4")
            img_b = _rel_capture_image_at_global(adapter, next_sec, region_mode="fast4")
            if img_a is None or img_b is None:
                break

            score = float(_rel_image_delta(adapter, img_a, img_b) or 0.0)
            baseline_for_decision = baseline if baseline > 0.0 else score
            baseline = (baseline_for_decision * 0.90 + score * 0.10) if baseline_for_decision > 0.0 else score
            is_candidate, reason = _rel_is_candidate(adapter, score, baseline_for_decision, previous_score)

            if next_frame == stride or next_frame % max(stride * 2, 1) == 0 or is_candidate:
                deltas = list(getattr(adapter, "_scan_last_region_deltas", []) or [])
                delta_text = ",".join(f"{d:.1f}" for d in deltas[:4])
                print(
                    f"📊 [scan-cut-auto] frame={next_frame} "
                    f"delta={score:.2f} baseline={baseline_for_decision:.2f} "
                    f"prev={previous_score:.2f} stride={stride} "
                    f"reason={reason or '-'} "
                    f"frame {last_frame}->{next_frame} "
                    f"{last_sec:.3f}s->{next_sec:.3f}s "
                    f"img={_rel_scan_backend_label(adapter)} fast4=[{delta_text}]",
                    flush=True,
                )

            if is_candidate:
                refined = _rel_refine_boundary(adapter, last_frame, next_frame, fps, reason)
                if refined:
                    stop_frame, stop_sec, final_score, final_regions, final_reason = refined
                    timeline_sec = max(0.0, float(clip_offset or 0.0) + float(stop_sec or 0.0))
                    frame_no = sec_to_frame(timeline_sec, fps)
                    row = {
                        "schema": "cut_boundary.v1",
                        "id": f"cut_{frame_no:08d}",
                        "time": timeline_sec,
                        "timeline_sec": timeline_sec,
                        "frame": frame_no,
                        "timeline_frame": frame_no,
                        "fps": fps,
                        "clip_idx": int(clip_idx),
                        "clip_local_sec": float(stop_sec or 0.0),
                        "source_path": filepath,
                        "score": float(final_score or 0.0),
                        "regions": int(final_regions or 0),
                        "reason": f"auto_pipeline_scan:{final_reason}",
                        "detector": "opencv-gray-relative",
                        "source": "visual",
                        "absolute": True,
                        "locked": True,
                    }
                    rows.append(row)
                    if callable(found_callback):
                        try:
                            found_callback(dict(row), list(rows))
                        except Exception:
                            pass
                    last_frame = max(next_frame, int(stop_frame) + resume_skip_frames)
                    previous_score = 0.0
                    baseline = 0.0
                    _report_progress(min(duration, last_frame / fps))
                    continue

            previous_score = score
            last_frame = next_frame
            _report_progress(min(duration, next_sec))
    except Exception:
        return []
    finally:
        cap = getattr(adapter, "_scan_cv2_capture", None)
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass
    _report_progress(duration, force=True)
    return normalize_cut_boundaries(rows, primary_fps=fps)


def _mean_abs_difference(frame_a: bytes | list[int], frame_b: bytes | list[int]) -> float:
    length = min(len(frame_a), len(frame_b))
    if length <= 0:
        return 0.0
    total = 0
    for index in range(length):
        total += abs(int(frame_a[index]) - int(frame_b[index]))
    return total / length



# === CUT_BOUNDARY_LEVEL_PROFILE_PATCH_V1 ===

CUT_BOUNDARY_LEVEL_CHOICES = (
    ("off", "사용안함"),
    ("low", "낮음 - 9개 중 십자가 4개"),
    ("medium", "중간 - 9개 중 꽉찬 십자가 5개"),
    ("high", "높음 - 9개 중 O모양 8개"),
)

CUT_BOUNDARY_GRID_PROFILES = {
    # 3x3 index:
    # 0 1 2
    # 3 4 5
    # 6 7 8
    "off": {
        "level": "off",
        "label": "사용안함",
        "mask": "off",
        "positions": (),
        "cell_count": 0,
    },
    "low": {
        "level": "low",
        "label": "낮음 - 9개 중 십자가 4개",
        "mask": "cross4",
        # 십자가 4개: 상/좌/우/하, 중앙 제외
        "positions": (1, 3, 5, 7),
        "cell_count": 4,
    },
    "medium": {
        "level": "medium",
        "label": "중간 - 9개 중 꽉찬 십자가 5개",
        "mask": "cross5",
        # X모양 5개: 네 모서리 + 중앙
        "positions": (1, 3, 4, 5, 7),
        "cell_count": 5,
    },
    "high": {
        "level": "high",
        "label": "높음 - 9개 중 O모양 8개",
        "mask": "o8",
        # O모양 8개: 중앙 제외 외곽 전체
        "positions": (0, 1, 2, 3, 5, 6, 7, 8),
        "cell_count": 8,
    },
}

def normalize_cut_boundary_level(value) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "false": "off",
        "0": "off",
        "none": "off",
        "disabled": "off",
        "disable": "off",
        "off": "off",
        "사용안함": "off",
        "사용 안함": "off",

        "low": "low",
        "낮음": "low",

        "mid": "medium",
        "middle": "medium",
        "medium": "medium",
        "중간": "medium",

        "high": "high",
        "높음": "high",

        "true": "medium",
        "1": "medium",
        "on": "medium",
        "enabled": "medium",
        "enable": "medium",
        "사용": "medium",
    }
    return aliases.get(raw, "medium")

def cut_boundary_level(settings: dict | None = None) -> str:
    settings = settings or {}

    # 새 설정 우선
    for key in (
        "scan_cut_boundary_level",
        "cut_boundary_level",
        "scan_cut_level",
    ):
        if key in settings:
            return normalize_cut_boundary_level(settings.get(key))

    # 기존 boolean 호환
    for key in (
        "scan_cut_enabled",
        "scan_cut_auto_enabled",
        "cut_boundary_enabled",
    ):
        if key in settings:
            return "medium" if bool(settings.get(key)) else "off"

    return "medium"

def cut_boundary_scan_profile(settings: dict | None = None) -> dict:
    level = cut_boundary_level(settings or {})
    profile = dict(CUT_BOUNDARY_GRID_PROFILES.get(level, CUT_BOUNDARY_GRID_PROFILES["medium"]))
    profile["choices"] = CUT_BOUNDARY_LEVEL_CHOICES
    return profile

def cut_boundary_enabled(settings: dict | None = None) -> bool:
    return cut_boundary_level(settings or {}) != "off"

def _grid_cell_slices(width: int, height: int):
    xs = [0, width // 3, (width * 2) // 3, width]
    ys = [0, height // 3, (height * 2) // 3, height]
    cells = []
    for r in range(3):
        for c in range(3):
            cells.append((xs[c], ys[r], xs[c + 1], ys[r + 1]))
    return cells

def _selected_grid_delta(prev_gray, cur_gray, positions) -> tuple[float, list[float]]:
    try:
        import cv2
        import numpy as np

        # 계산량을 낮추기 위해 270x270으로 통일
        prev = cv2.resize(prev_gray, (270, 270), interpolation=cv2.INTER_AREA)
        cur = cv2.resize(cur_gray, (270, 270), interpolation=cv2.INTER_AREA)

        cells = _grid_cell_slices(270, 270)
        deltas = []
        for idx in positions:
            x1, y1, x2, y2 = cells[int(idx)]
            p = prev[y1:y2, x1:x2]
            c = cur[y1:y2, x1:x2]
            d = float(np.mean(cv2.absdiff(p, c)))
            deltas.append(d)

        if not deltas:
            return 0.0, []
        return float(sum(deltas) / len(deltas)), deltas
    except Exception:
        return 0.0, []

def detect_media_cut_boundaries(
    media_path,
    *,
    clip_offset: float = 0.0,
    clip_idx: int = 0,
    sample_step_sec: float = 1.0,
    threshold: float = 24.0,
    progress_callback=None,
    found_callback=None,
    scan_profile: dict | None = None,
    sample_positions=None,
    sample_mask: str | None = None,
    **kwargs,
):
    """3x3 grid-profile cut detector.

    Levels:
    - off: disabled
    - low: cross4, 4/9
    - medium: x5, 5/9
    - high: o8, 8/9

    If OpenCV scan fails, fallback to the legacy detector.
    """
    try:
        import os
        import cv2
        import time

        try:
            from logger import get_logger
        except Exception:
            get_logger = None

        if scan_profile is None:
            try:
                from core.settings import load_settings
                scan_profile = cut_boundary_scan_profile(load_settings())
            except Exception:
                scan_profile = cut_boundary_scan_profile({})

        level = str((scan_profile or {}).get("level", "medium"))
        if level == "off":
            if get_logger:
                get_logger().log("  🎬 [컷 경계] 단계=사용안함, 분석을 건너뜁니다")
            return []

        positions = sample_positions
        if positions is None:
            positions = (scan_profile or {}).get("positions", ())
        positions = tuple(int(x) for x in (positions or ()))
        if not positions:
            return []

        mask = str(sample_mask or (scan_profile or {}).get("mask", ""))
        label = str((scan_profile or {}).get("label", level))

        cap = cv2.VideoCapture(str(media_path))
        if not cap.isOpened():
            raise RuntimeError("video open failed")

        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if fps <= 0.0 or frame_count <= 0:
            raise RuntimeError("invalid fps/frame_count")

        duration = frame_count / fps
        step = max(0.2, float(sample_step_sec or 1.0))
        step_frames = max(1, int(round(fps * step)))
        threshold = float(threshold or 24.0)

        # ✅ grid detector 안정화:
        # 기존 threshold=24를 그대로 쓰면 카메라 움직임/노출 변화도 컷으로 잡혀
        # 2초마다 컷이 생기는 문제가 발생한다.
        level_threshold_multiplier = {
            "low": 2.40,
            "medium": 2.00,
            "high": 1.70,
        }.get(level, 2.00)
        effective_threshold = max(threshold, threshold * level_threshold_multiplier)

        # 낮음/중간/높음은 "검사 칸 수"뿐 아니라 최소 컷 간격도 다르게 둔다.
        # 중간 기본 8초: 2초/4초/6초 식 오탐을 막는다.
        level_min_gap_sec = {
            "low": 12.0,
            "medium": 8.0,
            "high": 5.0,
        }.get(level, 8.0)

        clip_offset = float(clip_offset or 0.0)
        clip_idx = int(clip_idx or 0)

        if get_logger:
            get_logger().log(
                f"🔎 [scan-cut-grid] level={level} label={label} "
                f"mask={mask} cells={len(positions)}/9 threshold={threshold:.2f} effective={effective_threshold:.2f} min_gap={cooldown_sec:.1f}s "
                f"step={step:.2f}s source={os.path.basename(str(media_path))}"
            )

        rows = []
        prev_gray = None
        prev_t = 0.0
        last_emit_t = -9999.0
        cooldown_sec = max(level_min_gap_sec, step * 2.0)

        total_steps = max(1, int(frame_count / step_frames))
        step_i = 0

        for frame_no in range(0, frame_count, step_frames):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue

            t = frame_no / fps
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            if progress_callback:
                try:
                    progress_callback({
                        "clip_idx": clip_idx,
                        "percent": int(min(100, (step_i / max(1, total_steps)) * 100)),
                        "timestamp": t,
                        "duration": duration,
                        "detected": len(rows),
                    })
                except Exception:
                    pass

            if prev_gray is not None:
                delta, cell_deltas = _selected_grid_delta(prev_gray, gray, positions)

                # 선택된 칸 평균 delta 기준.
                # 추가로 선택 칸 중 절반 이상이 threshold의 70%를 넘으면 유효 컷으로 인정.
                required_ratio = {
                    "low": 0.75,
                    "medium": 0.80,
                    "high": 0.70,
                }.get(level, 0.80)

                strong_cells = sum(1 for d in cell_deltas if d >= effective_threshold * 0.70)
                required_cells = max(1, int(round(len(positions) * required_ratio)))
                enough_cells = strong_cells >= required_cells

                if delta >= effective_threshold and enough_cells and (t - last_emit_t) >= cooldown_sec:
                    sec = round(t, 3)
                    row = {
                        "time": sec,
                        "timeline_sec": round(clip_offset + sec, 3),
                        "clip_idx": clip_idx,
                        "source": "grid_profile",
                        "level": level,
                        "mask": mask,
                        "cell_count": len(positions),
                        "grid_positions": list(positions),
                        "delta": round(delta, 3),
                        "cell_deltas": [round(x, 3) for x in cell_deltas],
                        "threshold": threshold,
                        "prev_time": round(prev_t, 3),
                    }
                    rows.append(row)
                    last_emit_t = t

                    if get_logger:
                        get_logger().log(
                            f"📊 [scan-cut-grid] level={level} mask={mask} "
                            f"time={sec:.3f}s delta={delta:.2f} "
                            f"cells={strong_cells}/{len(positions)}"
                        )

                    if found_callback:
                        try:
                            found_callback(row, list(rows))
                        except Exception:
                            pass

            prev_gray = gray
            prev_t = t
            step_i += 1

        cap.release()

        if progress_callback:
            try:
                progress_callback({
                    "clip_idx": clip_idx,
                    "percent": 100,
                    "timestamp": duration,
                    "duration": duration,
                    "detected": len(rows),
                })
            except Exception:
                pass

        try:
            return normalize_cut_boundaries(rows)
        except Exception:
            return rows

    except Exception as exc:
        try:
            from logger import get_logger
            get_logger().log(f"  ⚠️ [컷 경계] grid detector 실패, legacy detector로 fallback: {exc}")
        except Exception:
            pass

        try:
            return _legacy_detect_media_cut_boundaries(
                media_path,
                clip_offset=clip_offset,
                clip_idx=clip_idx,
                sample_step_sec=sample_step_sec,
                threshold=threshold,
                progress_callback=progress_callback,
                found_callback=found_callback,
                **kwargs,
            )
        except TypeError:
            return _legacy_detect_media_cut_boundaries(
                media_path,
                clip_offset,
                clip_idx,
                sample_step_sec,
                threshold,
                progress_callback,
                found_callback,
            )


# === CUT_BOUNDARY_GRID_INTERVAL_FIX_V3 ===

def _cb_level_interval_sec(level: str) -> float:
    """Requested scan interval by cut-boundary level."""
    level = normalize_cut_boundary_level(level)
    return {
        "low": 2.0,       # 동영상 프레임 * 2
        "medium": 1.0,    # 동영상 프레임 동일
        "high": 0.5,      # 동영상 프레임 / 2
    }.get(level, 1.0)


def _cb_level_pyramid_steps(level: str) -> tuple[float, ...]:
    """Regression/refinement pyramid matched to the scan interval."""
    base = _cb_level_interval_sec(level)
    return (
        round(base, 3),
        round(base / 2.0, 3),
        round(base / 4.0, 3),
    )


def _cb_level_effective_threshold(level: str, threshold: float) -> float:
    """Make lower levels less sensitive while preserving the user threshold."""
    level = normalize_cut_boundary_level(level)
    mul = {
        "low": 2.40,
        "medium": 2.00,
        "high": 1.65,
    }.get(level, 2.00)
    return max(float(threshold or 24.0), float(threshold or 24.0) * mul)


def _cb_level_min_gap_sec(level: str) -> float:
    """Debounce false positives.

    This is separate from scan interval. Scan interval controls how often we
    inspect frames; min gap controls how close accepted cuts can be.
    """
    level = normalize_cut_boundary_level(level)
    return {
        "low": 10.0,
        "medium": 6.0,
        "high": 3.0,
    }.get(level, 6.0)


def _cb_read_gray_at(cap, frame_no: int):
    try:
        import cv2
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(frame_no)))
        ok, frame = cap.read()
        if not ok or frame is None:
            return None
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    except Exception:
        return None


def _cb_refine_cut_time_with_pyramid(
    cap,
    *,
    fps: float,
    coarse_time: float,
    positions,
    effective_threshold: float,
    level: str,
):
    """Refine candidate time using a backward pyramid.

    Example:
    - low:    2.0s -> 1.0s -> 0.5s
    - medium: 1.0s -> 0.5s -> 0.25s
    - high:   0.5s -> 0.25s -> 0.125s
    """
    try:
        import cv2

        steps = _cb_level_pyramid_steps(level)
        best_time = float(coarse_time)

        # Search only the previous base interval.
        window = max(steps[0], 0.25)
        start_t = max(0.0, best_time - window)
        end_t = best_time

        for step in steps:
            if step <= 0:
                continue

            t = start_t
            prev_gray = None
            local_best = best_time

            while t <= end_t + 1e-6:
                gray = _cb_read_gray_at(cap, int(round(t * fps)))
                if gray is not None and prev_gray is not None:
                    delta, cell_deltas = _selected_grid_delta(prev_gray, gray, positions)
                    strong_cells = sum(1 for d in cell_deltas if d >= effective_threshold * 0.70)
                    required_cells = max(1, int(round(len(positions) * 0.80)))
                    if delta >= effective_threshold and strong_cells >= required_cells:
                        local_best = round(t, 3)
                        break
                if gray is not None:
                    prev_gray = gray
                t += step

            best_time = local_best

            # Narrow next search window around the current best.
            start_t = max(0.0, best_time - step)
            end_t = min(float(coarse_time), best_time + step)

        return round(float(best_time), 3)
    except Exception:
        return round(float(coarse_time), 3)


def detect_media_cut_boundaries(
    media_path,
    *,
    clip_offset: float = 0.0,
    clip_idx: int = 0,
    sample_step_sec: float = 1.0,
    threshold: float = 24.0,
    progress_callback=None,
    found_callback=None,
    scan_profile: dict | None = None,
    sample_positions=None,
    sample_mask: str | None = None,
    **kwargs,
):
    """Stable 3x3 grid-profile cut detector.

    Levels:
    - off: disabled
    - low:    cross4, 4/9, scan every 2.0s
    - medium: x5,     5/9, scan every 1.0s
    - high:   o8,     8/9, scan every 0.5s

    Regression pyramid follows the same interval ratio:
    - low:    2.0 -> 1.0 -> 0.5
    - medium: 1.0 -> 0.5 -> 0.25
    - high:   0.5 -> 0.25 -> 0.125
    """
    try:
        import os
        import cv2

        try:
            from logger import get_logger
        except Exception:
            get_logger = None

        if scan_profile is None:
            try:
                from core.settings import load_settings
                scan_profile = cut_boundary_scan_profile(load_settings())
            except Exception:
                scan_profile = cut_boundary_scan_profile({})

        level = normalize_cut_boundary_level((scan_profile or {}).get("level", "medium"))

        if level == "off":
            if get_logger:
                get_logger().log("  🎬 [컷 경계] 단계=사용안함, 분석을 건너뜁니다")
            return []

        positions = sample_positions
        if positions is None:
            positions = (scan_profile or {}).get("positions", ())
        positions = tuple(int(x) for x in (positions or ()))
        if not positions:
            return []

        mask = str(sample_mask or (scan_profile or {}).get("mask", ""))
        label = str((scan_profile or {}).get("label", level))

        cap = cv2.VideoCapture(str(media_path))
        if not cap.isOpened():
            raise RuntimeError("video open failed")

        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if fps <= 0.0 or frame_count <= 0:
            raise RuntimeError("invalid fps/frame_count")

        duration = frame_count / fps

        # ✅ 요청 기준 강제 적용
        scan_interval_sec = _cb_level_interval_sec(level)
        step_frames = max(1, int(round(fps * scan_interval_sec)))

        threshold = float(threshold or 24.0)
        effective_threshold = _cb_level_effective_threshold(level, threshold)
        min_gap_sec = _cb_level_min_gap_sec(level)
        pyramid_steps = _cb_level_pyramid_steps(level)

        clip_offset = float(clip_offset or 0.0)
        clip_idx = int(clip_idx or 0)

        if get_logger:
            get_logger().log(
                f"🔎 [scan-cut-grid-v3] level={level} label={label} "
                f"mask={mask} cells={len(positions)}/9 "
                f"interval={scan_interval_sec:.3f}s pyramid={pyramid_steps} "
                f"threshold={threshold:.2f} effective={effective_threshold:.2f} "
                f"min_gap={min_gap_sec:.1f}s source={os.path.basename(str(media_path))}"
            )

        rows = []
        prev_gray = None
        prev_t = 0.0
        last_emit_t = -999999.0

        total_steps = max(1, int(frame_count / step_frames))
        step_i = 0

        for frame_no in range(0, frame_count, step_frames):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue

            t = frame_no / fps
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            if progress_callback:
                try:
                    progress_callback({
                        "clip_idx": clip_idx,
                        "percent": int(min(100, (step_i / max(1, total_steps)) * 100)),
                        "timestamp": t,
                        "duration": duration,
                        "detected": len(rows),
                    })
                except Exception:
                    pass

            if prev_gray is not None:
                delta, cell_deltas = _selected_grid_delta(prev_gray, gray, positions)

                required_ratio = {
                    "low": 0.85,
                    "medium": 0.80,
                    "high": 0.70,
                }.get(level, 0.80)

                strong_cells = sum(1 for d in cell_deltas if d >= effective_threshold * 0.70)
                required_cells = max(1, int(round(len(positions) * required_ratio)))
                enough_cells = strong_cells >= required_cells

                if (
                    delta >= effective_threshold
                    and enough_cells
                    and (t - last_emit_t) >= min_gap_sec
                ):
                    refined_sec = _cb_refine_cut_time_with_pyramid(
                        cap,
                        fps=fps,
                        coarse_time=t,
                        positions=positions,
                        effective_threshold=effective_threshold,
                        level=level,
                    )

                    # refine 결과도 min_gap 안쪽이면 버림
                    if refined_sec - last_emit_t < min_gap_sec:
                        prev_gray = gray
                        prev_t = t
                        step_i += 1
                        continue

                    row = {
                        "time": round(refined_sec, 3),
                        "timeline_sec": round(clip_offset + refined_sec, 3),
                        "clip_idx": clip_idx,
                        "source": "grid_profile_v3",
                        "level": level,
                        "mask": mask,
                        "cell_count": len(positions),
                        "grid_positions": list(positions),
                        "delta": round(delta, 3),
                        "cell_deltas": [round(x, 3) for x in cell_deltas],
                        "threshold": threshold,
                        "effective_threshold": round(effective_threshold, 3),
                        "scan_interval_sec": scan_interval_sec,
                        "pyramid_steps": list(pyramid_steps),
                        "min_gap_sec": min_gap_sec,
                        "prev_time": round(prev_t, 3),
                        "coarse_time": round(t, 3),
                    }

                    rows.append(row)
                    last_emit_t = refined_sec

                    if get_logger:
                        get_logger().log(
                            f"📊 [scan-cut-grid-v3] level={level} mask={mask} "
                            f"coarse={t:.3f}s refined={refined_sec:.3f}s "
                            f"delta={delta:.2f} cells={strong_cells}/{len(positions)}"
                        )

                    if found_callback:
                        try:
                            found_callback(row, list(rows))
                        except Exception:
                            pass

            prev_gray = gray
            prev_t = t
            step_i += 1

        cap.release()

        if progress_callback:
            try:
                progress_callback({
                    "clip_idx": clip_idx,
                    "percent": 100,
                    "timestamp": duration,
                    "duration": duration,
                    "detected": len(rows),
                })
            except Exception:
                pass

        try:
            return normalize_cut_boundaries(rows)
        except Exception:
            return rows

    except Exception as exc:
        try:
            from logger import get_logger
            get_logger().log(
                f"  ⚠️ [컷 경계] grid-v3 detector 실패, legacy detector로 fallback: {exc}"
            )
        except Exception:
            pass

        try:
            return _legacy_detect_media_cut_boundaries(
                media_path,
                clip_offset=clip_offset,
                clip_idx=clip_idx,
                sample_step_sec=sample_step_sec,
                threshold=threshold,
                progress_callback=progress_callback,
                found_callback=found_callback,
                **kwargs,
            )
        except Exception:
            return []


# === CUT_BOUNDARY_CROSS5_LEVEL_OVERRIDE ===

CUT_BOUNDARY_LEVEL_CHOICES = (
    ("off", "사용안함"),
    ("low", "낮음"),
    ("medium", "중간"),
    ("high", "높음"),
)

CUT_BOUNDARY_GRID_PROFILES = {
    # 3x3 index:
    # 0 1 2
    # 3 4 5
    # 6 7 8
    "off": {
        "level": "off",
        "label": "사용안함",
        "mask": "off",
        "positions": (),
        "cell_count": 0,
    },
    "low": {
        "level": "low",
        "label": "낮음 - 9개 중 십자가 4개",
        "mask": "cross4",
        "positions": (1, 3, 5, 7),
        "cell_count": 4,
    },
    "medium": {
        "level": "medium",
        "label": "중간 - 9개 중 꽉찬 십자가 5개",
        "mask": "cross5",
        "positions": (1, 3, 4, 5, 7),
        "cell_count": 5,
    },
    "high": {
        "level": "high",
        "label": "높음 - 9개 중 O모양 8개",
        "mask": "o8",
        "positions": (0, 1, 2, 3, 5, 6, 7, 8),
        "cell_count": 8,
    },
}

def normalize_cut_boundary_level(value) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "사용안함": "off",
        "사용 안함": "off",
        "미사용": "off",
        "off": "off",
        "false": "off",
        "0": "off",
        "disabled": "off",
        "disable": "off",
        "none": "off",

        "낮음": "low",
        "low": "low",

        "중간": "medium",
        "medium": "medium",
        "mid": "medium",
        "middle": "medium",
        "사용": "medium",
        "on": "medium",
        "true": "medium",
        "1": "medium",
        "enabled": "medium",

        "높음": "high",
        "high": "high",
    }
    return aliases.get(raw, "medium")

def cut_boundary_level(settings: dict | None = None) -> str:
    settings = settings or {}

    for key in (
        "scan_cut_boundary_level",
        "cut_boundary_level",
        "scan_cut_level",
    ):
        if key in settings:
            return normalize_cut_boundary_level(settings.get(key))

    for key in (
        "cut_boundary_detection_enabled",
        "scan_cut_enabled",
        "scan_cut_auto_enabled",
        "cut_boundary_enabled",
    ):
        if key in settings:
            return "medium" if bool(settings.get(key)) else "off"

    return "medium"

def cut_boundary_scan_profile(settings: dict | None = None) -> dict:
    level = cut_boundary_level(settings or {})
    profile = dict(CUT_BOUNDARY_GRID_PROFILES.get(level, CUT_BOUNDARY_GRID_PROFILES["medium"]))
    profile["choices"] = CUT_BOUNDARY_LEVEL_CHOICES
    return profile

def cut_boundary_enabled(settings: dict | None = None) -> bool:
    return cut_boundary_level(settings or {}) != "off"

