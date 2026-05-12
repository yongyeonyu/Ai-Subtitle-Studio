from __future__ import annotations

"""Local visual cut-jump helpers for frame-by-frame editor transport."""

from statistics import median
from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _metric_median(history: list[dict] | None, key: str, default: float) -> float:
    values = [
        _safe_float(item.get(key), default)
        for item in list(history or [])
        if isinstance(item, dict) and item.get(key) is not None
    ]
    if not values:
        return float(default)
    try:
        return float(median(values))
    except Exception:
        return float(default)


def _make_flow_engine(cv2_mod, backend_preference: str = "dis"):
    backend = str(backend_preference or "dis").strip().lower()
    if backend != "farneback" and hasattr(cv2_mod, "DISOpticalFlow_create"):
        try:
            preset = getattr(cv2_mod, "DISOPTICAL_FLOW_PRESET_ULTRAFAST", 0)
            return cv2_mod.DISOpticalFlow_create(preset), "opencv_dis_ultrafast"
        except Exception:
            pass
    return None, "opencv_farneback"


def create_visual_cut_flow_engine(cv2_mod, *, backend_preference: str = "dis"):
    return _make_flow_engine(cv2_mod, backend_preference=backend_preference)


def prepare_visual_cut_frame(
    frame_bgr,
    cv2_mod,
    *,
    max_width: int = 960,
    blur_size: int = 5,
    canny_low: int = 64,
    canny_high: int = 160,
) -> dict[str, Any] | None:
    if frame_bgr is None:
        return None
    try:
        height, width = frame_bgr.shape[:2]
    except Exception:
        return None
    if width <= 0 or height <= 0:
        return None

    max_width = max(160, min(int(max_width or 960), 4096))
    if width > max_width:
        scale = max_width / float(width)
        frame_bgr = cv2_mod.resize(
            frame_bgr,
            (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
            interpolation=cv2_mod.INTER_AREA,
        )

    gray = cv2_mod.cvtColor(frame_bgr, cv2_mod.COLOR_BGR2GRAY)
    blur_size = max(1, int(blur_size or 5))
    if blur_size % 2 == 0:
        blur_size += 1
    if blur_size > 1:
        flow_gray = cv2_mod.GaussianBlur(gray, (blur_size, blur_size), 0)
    else:
        flow_gray = gray

    edges = cv2_mod.Canny(flow_gray, max(0, int(canny_low or 64)), max(1, int(canny_high or 160)))
    return {
        "gray": flow_gray,
        "edges": edges,
        "width": int(flow_gray.shape[1]),
        "height": int(flow_gray.shape[0]),
    }


def native_visual_cut_coarse_series(
    payloads: list[dict[str, Any]] | None,
    *,
    region_threshold: float = 24.0,
    diff_threshold: float = 32.0,
) -> list[dict[str, Any]] | None:
    rows = [item for item in list(payloads or []) if isinstance(item, dict) and item.get("edges") is not None]
    if len(rows) < 2:
        return []
    try:
        from core.native_cut_boundary import gray_edge_series as native_gray_edge_series

        native_rows = native_gray_edge_series(
            [item.get("edges") for item in rows],
            region_threshold=float(region_threshold),
            diff_threshold=float(diff_threshold),
        )
    except Exception:
        native_rows = None
    if not isinstance(native_rows, list):
        return None

    out: list[dict[str, Any]] = []
    for idx, item in enumerate(native_rows):
        if not isinstance(item, dict):
            return None
        left = rows[idx]
        right = rows[idx + 1]
        left_frame = int(left.get("global_frame", 0) or 0)
        right_frame = int(right.get("global_frame", 0) or 0)
        edge_diff = _safe_float(item.get("diff")) / 255.0
        out.append(
            {
                "score": _safe_float(item.get("score")) / 255.0,
                "edge_diff": float(edge_diff),
                "edge_residual": float(edge_diff),
                "coverage": _safe_float(item.get("coverage")),
                "coarse_native_regions": int(item.get("regions", 0) or 0),
                "coarse_native_deltas": [float(value) for value in list(item.get("deltas") or [])],
                "coarse_native_raw": _safe_float(item.get("score")) / 255.0,
                "boundary_frame": int(min(left_frame, right_frame)),
                "boundary_sec": float(min(_safe_float(left.get("global_sec")), _safe_float(right.get("global_sec")))),
                "left_frame": int(left_frame),
                "right_frame": int(right_frame),
                "analysis_width": int(left.get("width", left.get("analysis_width", 0)) or 0),
                "source_changed": bool(left.get("source_path") != right.get("source_path")),
                "interval_start_frame": int(min(left_frame, right_frame)),
                "interval_end_frame": int(max(left_frame, right_frame)),
                "interval_stride_frames": int(abs(right_frame - left_frame)),
                "backend": "native_edge_series",
                "metrics_backend": "cpp_native",
                "hard_cut_like": False,
                "coarse_native": True,
            }
        )
    return out


def visual_cut_pair_metrics(
    left_frame: dict[str, Any] | None,
    right_frame: dict[str, Any] | None,
    cv2_mod,
    *,
    flow_engine=None,
    backend_preference: str = "dis",
    diff_threshold: float = 32.0,
) -> dict[str, float | str | bool] | None:
    if not isinstance(left_frame, dict) or not isinstance(right_frame, dict):
        return None

    prev_gray = left_frame.get("gray")
    next_gray = right_frame.get("gray")
    prev_edges = left_frame.get("edges")
    next_edges = right_frame.get("edges")
    if prev_gray is None or next_gray is None or prev_edges is None or next_edges is None:
        return None

    try:
        if prev_gray.shape != next_gray.shape or prev_edges.shape != next_edges.shape:
            return None
    except Exception:
        return None

    backend = "flow_unavailable"
    flow = None
    if flow_engine is None:
        flow_engine, backend = _make_flow_engine(cv2_mod, backend_preference=backend_preference)

    if flow_engine is not None:
        try:
            flow = flow_engine.calc(prev_gray, next_gray, None)
            backend = "opencv_dis_ultrafast"
        except Exception:
            flow = None

    if flow is None and hasattr(cv2_mod, "calcOpticalFlowFarneback"):
        try:
            flow = cv2_mod.calcOpticalFlowFarneback(
                prev_gray,
                next_gray,
                None,
                0.5,
                2,
                15,
                2,
                5,
                1.1,
                0,
            )
            backend = "opencv_farneback"
        except Exception:
            flow = None

    if flow is None:
        return None

    metrics_backend = "python_numpy"
    native_metrics = None
    try:
        from core.native_cut_boundary import dense_flow_pair_metrics as native_dense_flow_pair_metrics

        native_metrics = native_dense_flow_pair_metrics(
            prev_edges,
            next_edges,
            flow,
            diff_threshold=float(diff_threshold or 32.0),
        )
    except Exception:
        native_metrics = None

    if isinstance(native_metrics, dict):
        diff_before = _safe_float(native_metrics.get("diff")) / 255.0
        coverage = _safe_float(native_metrics.get("coverage"))
        residual = _safe_float(native_metrics.get("residual"), diff_before * 255.0) / 255.0
        residual_ratio = _safe_float(native_metrics.get("residual_ratio"), residual / max(diff_before, 1e-6))
        mean_mag = _safe_float(native_metrics.get("mean_motion_px"))
        coherence = _safe_float(native_metrics.get("coherence"))
        metrics_backend = "cpp_native"
    else:
        try:
            import numpy as np
        except Exception:
            return None

        diff = np.abs(prev_edges.astype(np.float32) - next_edges.astype(np.float32))
        diff_before = float(diff.mean()) / 255.0
        coverage = float((diff >= float(diff_threshold or 32.0)).mean())
        height, width = prev_edges.shape[:2]
        grid_x, grid_y = np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
        map_x = grid_x - flow[:, :, 0].astype(np.float32)
        map_y = grid_y - flow[:, :, 1].astype(np.float32)
        try:
            warped = cv2_mod.remap(
                prev_edges,
                map_x,
                map_y,
                interpolation=cv2_mod.INTER_LINEAR,
                borderMode=cv2_mod.BORDER_REPLICATE,
            )
            residual = float(np.abs(warped.astype(np.float32) - next_edges.astype(np.float32)).mean()) / 255.0
        except Exception:
            residual = diff_before

        fx = flow[:, :, 0].astype(np.float32)
        fy = flow[:, :, 1].astype(np.float32)
        mag = np.sqrt(fx ** 2 + fy ** 2)
        mean_mag = float(mag.mean())
        mean_fx = float(fx.mean())
        mean_fy = float(fy.mean())
        coherence = float((mean_fx * mean_fx + mean_fy * mean_fy) ** 0.5 / max(mean_mag, 1e-6))
        residual_ratio = residual / max(diff_before, 1e-6)

    return {
        "edge_diff": float(diff_before),
        "edge_residual": float(residual),
        "residual_ratio": float(residual_ratio),
        "coverage": float(coverage),
        "mean_motion_px": float(mean_mag),
        "coherence": float(coherence),
        "backend": str(backend),
        "metrics_backend": str(metrics_backend),
        "hard_cut_like": bool(residual_ratio >= 0.94 and coherence <= 0.72),
    }


def score_visual_cut_metrics(
    metrics: dict[str, Any] | None,
    *,
    history: list[dict] | None = None,
    settings: dict | None = None,
) -> dict[str, Any] | None:
    if not isinstance(metrics, dict):
        return None

    data = dict(settings or {})
    min_edge_residual = max(0.010, _safe_float(data.get("scan_cut_live_visual_min_edge_residual"), 0.045))
    min_edge_diff = max(0.010, _safe_float(data.get("scan_cut_live_visual_min_edge_diff"), 0.060))
    min_residual_ratio = max(0.20, _safe_float(data.get("scan_cut_live_visual_min_residual_ratio"), 0.78))
    min_motion_jump = max(1.0, _safe_float(data.get("scan_cut_live_visual_min_motion_jump"), 2.3))
    max_coherence = _clamp(_safe_float(data.get("scan_cut_live_visual_max_coherence"), 0.82), 0.20, 0.99)
    residual_baseline_scale = max(1.0, _safe_float(data.get("scan_cut_live_visual_residual_baseline_scale"), 1.35))
    edge_baseline_scale = max(1.0, _safe_float(data.get("scan_cut_live_visual_edge_baseline_scale"), 1.08))

    baseline_residual = _metric_median(history, "edge_residual", 0.032)
    baseline_diff = _metric_median(history, "edge_diff", 0.058)
    baseline_motion = _metric_median(history, "mean_motion_px", 1.5)

    target_residual = max(min_edge_residual, baseline_residual * residual_baseline_scale)
    target_diff = max(min_edge_diff, baseline_diff * edge_baseline_scale)
    target_coherence_delta = max(0.05, 1.0 - max_coherence)

    edge_residual = _safe_float(metrics.get("edge_residual"))
    edge_diff = _safe_float(metrics.get("edge_diff"))
    residual_ratio = _safe_float(metrics.get("residual_ratio"))
    mean_motion = _safe_float(metrics.get("mean_motion_px"))
    coherence = _safe_float(metrics.get("coherence"), 1.0)

    residual_jump = edge_residual / max(baseline_residual, 1e-6)
    diff_jump = edge_diff / max(baseline_diff, 1e-6)
    motion_jump = mean_motion / max(baseline_motion, 1e-6)

    score = (
        min(edge_residual / max(target_residual, 1e-6), 3.0) * 0.38
        + min(residual_ratio / max(min_residual_ratio, 1e-6), 2.0) * 0.22
        + min(motion_jump / max(min_motion_jump, 1e-6), 3.0) * 0.18
        + min(edge_diff / max(target_diff, 1e-6), 2.0) * 0.12
        + min(max(0.0, 1.0 - coherence) / target_coherence_delta, 2.0) * 0.10
    )
    if bool(metrics.get("source_changed")):
        score += 0.18

    return {
        **metrics,
        "score": float(score),
        "residual_jump": float(residual_jump),
        "diff_jump": float(diff_jump),
        "motion_jump": float(motion_jump),
        "baseline_edge_residual": float(baseline_residual),
        "baseline_edge_diff": float(baseline_diff),
        "baseline_motion_px": float(baseline_motion),
        "target_edge_residual": float(target_residual),
        "target_edge_diff": float(target_diff),
        "min_residual_ratio": float(min_residual_ratio),
        "max_coherence": float(max_coherence),
    }


def score_visual_cut_coarse_metrics(
    metrics: dict[str, Any] | None,
    *,
    history: list[dict] | None = None,
    settings: dict | None = None,
) -> dict[str, Any] | None:
    if not isinstance(metrics, dict):
        return None

    data = dict(settings or {})
    baseline_diff = _metric_median(history, "edge_diff", 0.030)
    baseline_cov = _metric_median(history, "coverage", 0.025)
    baseline_raw = _metric_median(history, "coarse_native_raw", 0.030)

    edge_diff = _safe_float(metrics.get("edge_diff"))
    coverage = _safe_float(metrics.get("coverage"))
    raw_score = _safe_float(metrics.get("coarse_native_raw"), edge_diff)
    regions = max(0, int(metrics.get("coarse_native_regions", 0) or 0))
    min_regions = max(1, int(data.get("scan_cut_live_native_coarse_min_regions", 2) or 2))

    target_diff = max(0.030, baseline_diff * max(1.05, _safe_float(data.get("scan_cut_live_native_coarse_diff_scale"), 1.18)))
    target_cov = max(0.020, baseline_cov * max(1.05, _safe_float(data.get("scan_cut_live_native_coarse_coverage_scale"), 1.12)))
    target_raw = max(0.030, baseline_raw * max(1.05, _safe_float(data.get("scan_cut_live_native_coarse_raw_scale"), 1.20)))

    diff_jump = edge_diff / max(baseline_diff, 1e-6)
    coverage_jump = coverage / max(baseline_cov, 1e-6)
    raw_jump = raw_score / max(baseline_raw, 1e-6)
    region_boost = min(float(regions) / float(max(min_regions, 1)), 1.5)

    score = (
        min(raw_score / max(target_raw, 1e-6), 3.5) * 0.46
        + min(edge_diff / max(target_diff, 1e-6), 3.0) * 0.24
        + min(coverage / max(target_cov, 1e-6), 3.0) * 0.18
        + min(raw_jump, 3.0) * 0.07
        + region_boost * 0.05
    )
    if bool(metrics.get("source_changed")):
        score += 0.18

    return {
        **metrics,
        "score": float(score),
        "diff_jump": float(diff_jump),
        "coverage_jump": float(coverage_jump),
        "raw_jump": float(raw_jump),
        "baseline_edge_diff": float(baseline_diff),
        "baseline_coverage": float(baseline_cov),
        "baseline_coarse_raw": float(baseline_raw),
        "target_edge_diff": float(target_diff),
        "target_coverage": float(target_cov),
        "target_coarse_raw": float(target_raw),
        "min_regions": int(min_regions),
    }


def is_visual_cut_peak(
    prev_metrics: dict[str, Any] | None,
    current_metrics: dict[str, Any] | None,
    next_metrics: dict[str, Any] | None,
    *,
    history: list[dict] | None = None,
    settings: dict | None = None,
) -> dict[str, Any]:
    current = score_visual_cut_metrics(current_metrics, history=history, settings=settings)
    if current is None:
        return {"passed": False, "reason": "invalid_current"}

    prev_score = score_visual_cut_metrics(prev_metrics, history=history, settings=settings)
    next_score = score_visual_cut_metrics(next_metrics, history=history, settings=settings)
    if prev_score is None or next_score is None:
        return {"passed": False, "reason": "invalid_neighbors", **current}

    data = dict(settings or {})
    min_score = max(0.5, _safe_float(data.get("scan_cut_live_visual_min_score"), 1.05))
    peak_ratio = max(1.0, _safe_float(data.get("scan_cut_live_visual_peak_ratio"), 1.12))
    peak_margin = max(0.0, _safe_float(data.get("scan_cut_live_visual_peak_margin"), 0.12))
    abs_motion_px = max(0.0, _safe_float(data.get("scan_cut_live_visual_abs_motion_px"), 7.5))

    local_peak = (
        current["score"] >= max(prev_score["score"] * peak_ratio, prev_score["score"] + peak_margin)
        and current["score"] >= max(next_score["score"] * peak_ratio, next_score["score"] + peak_margin * 0.5)
    )
    hard_signal = (
        current["edge_residual"] >= current["target_edge_residual"]
        and current["edge_diff"] >= current["target_edge_diff"]
        and current["residual_ratio"] >= current["min_residual_ratio"]
        and (
            current["motion_jump"] >= max(1.0, _safe_float(data.get("scan_cut_live_visual_min_motion_jump"), 2.3))
            or current["mean_motion_px"] >= abs_motion_px
            or bool(current.get("source_changed"))
        )
    )

    passed = bool(local_peak and hard_signal and current["score"] >= min_score)
    return {
        **current,
        "passed": passed,
        "reason": "peak_cut" if passed else "below_peak_threshold",
        "local_peak": bool(local_peak),
        "prev_score": float(prev_score["score"]),
        "next_score": float(next_score["score"]),
        "min_score": float(min_score),
    }
