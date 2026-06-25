"""Shared visual cut-jump scoring helpers for manual scan and auto cut workers."""

from __future__ import annotations

from typing import Any

try:
    from core.native_cut_boundary import (
        dense_flow_pair_metrics as _native_dense_flow_pair_metrics,
        native_cut_boundary_enabled as _native_cut_boundary_enabled,
    )
except Exception:
    _native_dense_flow_pair_metrics = None

    def _native_cut_boundary_enabled() -> bool:
        return False


_MODE_CELLS = {
    "fast4": ((1, 0), (0, 1), (2, 1), (1, 2)),
    "cross5": ((1, 0), (0, 1), (1, 1), (2, 1), (1, 2)),
    "full9": (
        (0, 0), (1, 0), (2, 0),
        (0, 1), (1, 1), (2, 1),
        (0, 2), (1, 2), (2, 2),
    ),
}


def _settings_float(settings: dict | None, key: str, default: float) -> float:
    try:
        return float((settings or {}).get(key, default))
    except Exception:
        return float(default)


def _settings_int(settings: dict | None, key: str, default: int) -> int:
    try:
        return int((settings or {}).get(key, default))
    except Exception:
        return int(default)


def _clamp(value: float, low: float, high: float) -> float:
    return max(float(low), min(float(high), float(value)))


def _clamp01(value: float) -> float:
    return _clamp(value, 0.0, 1.0)


def visual_cut_mode_width(mode: str, settings: dict | None = None) -> int:
    mode_key = str(mode or "fast4").strip().lower()
    if mode_key == "full9":
        return max(160, min(1920, _settings_int(settings, "scan_cut_visual_full_width", 960)))
    if mode_key == "cross5":
        return max(160, min(1280, _settings_int(settings, "scan_cut_visual_cross_width", 480)))
    return max(120, min(960, _settings_int(settings, "scan_cut_visual_fast_width", 320)))


def _mode_cells(mode: str) -> tuple[tuple[int, int], ...]:
    return _MODE_CELLS.get(str(mode or "fast4").strip().lower(), _MODE_CELLS["fast4"])


def _safe_canny(gray, cv2_mod, low: int, high: int):
    if not hasattr(cv2_mod, "Canny"):
        return None
    try:
        return cv2_mod.Canny(gray, int(low), int(high))
    except Exception:
        return None


def _gray_histogram(gray, *, bins: int = 32):
    try:
        import numpy as np
    except Exception:
        return None
    try:
        hist, _edges = np.histogram(gray, bins=max(8, int(bins or 32)), range=(0, 256))
        total = float(hist.sum())
        if total <= 0.0:
            return None
        return hist.astype("float32") / total
    except Exception:
        return None


def _perceptual_hash(gray, cv2_mod, *, size: int = 32, bits: int = 8):
    try:
        import numpy as np
    except Exception:
        return None
    try:
        size = max(8, int(size or 32))
        bits = max(4, min(size, int(bits or 8)))
        small = cv2_mod.resize(gray, (size, size), interpolation=cv2_mod.INTER_AREA)
        if hasattr(cv2_mod, "dct"):
            coeffs = cv2_mod.dct(small.astype("float32"))
            block = coeffs[:bits, :bits]
        else:
            block = small[:bits, :bits].astype("float32")
        flat = block.flatten()
        if flat.size <= 1:
            return None
        median = float(np.median(flat[1:]))
        return (flat > median).astype("uint8")
    except Exception:
        return None


def _hist_delta(prev_hist, next_hist) -> float:
    try:
        import numpy as np
    except Exception:
        return 0.0
    if prev_hist is None or next_hist is None:
        return 0.0
    try:
        return float(1.0 - np.minimum(prev_hist, next_hist).sum())
    except Exception:
        return 0.0


def _hash_delta(prev_hash, next_hash) -> float:
    try:
        import numpy as np
    except Exception:
        return 0.0
    if prev_hash is None or next_hash is None:
        return 0.0
    try:
        if prev_hash.shape != next_hash.shape or prev_hash.size <= 0:
            return 0.0
        return float(np.count_nonzero(prev_hash != next_hash) / float(prev_hash.size))
    except Exception:
        return 0.0


def _ssim_lite(prev_gray, next_gray) -> float:
    try:
        import numpy as np
    except Exception:
        return 1.0
    try:
        a = prev_gray.astype("float32")
        b = next_gray.astype("float32")
        mean_a = float(a.mean())
        mean_b = float(b.mean())
        var_a = float(((a - mean_a) ** 2).mean())
        var_b = float(((b - mean_b) ** 2).mean())
        cov = float(((a - mean_a) * (b - mean_b)).mean())
        c1 = 6.5025
        c2 = 58.5225
        numerator = (2.0 * mean_a * mean_b + c1) * (2.0 * cov + c2)
        denominator = (mean_a * mean_a + mean_b * mean_b + c1) * (var_a + var_b + c2)
        if denominator <= 0.0:
            return 1.0
        return _clamp01(numerator / denominator)
    except Exception:
        return 1.0


def _should_skip_flow(
    mode: str,
    gray_mean: float,
    pixel_ratio: float,
    edge_ratio: float,
    settings: dict | None = None,
) -> bool:
    mode_key = str(mode or "fast4").strip().lower()
    if mode_key != "fast4":
        return False
    gate_gray = max(2.0, _settings_float(settings, "scan_cut_visual_fast_gate_gray_min", 14.0))
    gate_pixel = max(0.01, _settings_float(settings, "scan_cut_visual_fast_gate_pixel_ratio_min", 0.18))
    gate_edge = max(0.01, _settings_float(settings, "scan_cut_visual_fast_gate_edge_ratio_min", 0.16))
    return (
        float(gray_mean) < gate_gray
        and float(pixel_ratio) < gate_pixel
        and float(edge_ratio) < gate_edge
    )


def build_visual_cut_sample(
    frame_image: Any,
    cv2_mod,
    *,
    mode: str = "fast4",
    width: int | None = None,
    settings: dict | None = None,
) -> dict[str, Any] | None:
    if frame_image is None or cv2_mod is None:
        return None

    try:
        import numpy as np
    except Exception:
        np = None

    try:
        shape = frame_image.shape
    except Exception:
        return None
    if len(shape) < 2:
        return None

    frame = frame_image
    src_h, src_w = int(shape[0]), int(shape[1])
    if src_w <= 0 or src_h <= 0:
        return None

    target_w = int(width or visual_cut_mode_width(mode, settings))
    target_w = max(32, target_w)
    if src_w > target_w:
        scale = target_w / float(src_w)
        target_h = max(18, int(round(src_h * scale)))
        try:
            frame = cv2_mod.resize(frame_image, (target_w, target_h), interpolation=cv2_mod.INTER_AREA)
        except Exception:
            frame = frame_image
    else:
        target_h = src_h

    try:
        if len(frame.shape) >= 3 and int(frame.shape[2]) >= 3:
            gray = cv2_mod.cvtColor(frame, cv2_mod.COLOR_BGR2GRAY)
        else:
            gray = frame
    except Exception:
        return None

    if np is not None:
        try:
            gray = np.ascontiguousarray(gray, dtype=np.uint8)
        except Exception:
            pass

    edge_low = max(8, min(180, _settings_int(settings, "scan_cut_visual_edge_low", 64)))
    edge_high = max(edge_low + 8, min(255, _settings_int(settings, "scan_cut_visual_edge_high", 160)))
    edges = _safe_canny(gray, cv2_mod, edge_low, edge_high)
    hist_bins = max(8, min(128, _settings_int(settings, "scan_cut_visual_hist_bins", 32)))

    return {
        "mode": str(mode or "fast4").lower(),
        "gray": gray,
        "edges": edges,
        "histogram": _gray_histogram(gray, bins=hist_bins),
        "phash": _perceptual_hash(gray, cv2_mod),
        "shape": tuple(int(x) for x in gray.shape[:2]),
    }


def _grid_bounds(height: int, width: int, cell_x: int, cell_y: int) -> tuple[int, int, int, int]:
    xs = (0, int(width / 3), int(width * 2 / 3), int(width))
    ys = (0, int(height / 3), int(height * 2 / 3), int(height))
    return xs[cell_x], xs[cell_x + 1], ys[cell_y], ys[cell_y + 1]


def _calc_flow(prev_gray, next_gray, cv2_mod, *, settings: dict | None = None):
    backend_preference = str((settings or {}).get("scan_cut_visual_flow_backend", "dis") or "dis").strip().lower()
    flow_engine = None
    if backend_preference != "farneback" and hasattr(cv2_mod, "DISOpticalFlow_create"):
        try:
            preset = getattr(cv2_mod, "DISOPTICAL_FLOW_PRESET_ULTRAFAST", 0)
            flow_engine = cv2_mod.DISOpticalFlow_create(preset)
        except Exception:
            flow_engine = None
    if flow_engine is not None:
        try:
            flow = flow_engine.calc(prev_gray, next_gray, None)
            if flow is not None:
                return flow, "opencv_dis_ultrafast"
        except Exception:
            pass
    if not hasattr(cv2_mod, "calcOpticalFlowFarneback"):
        return None, "flow_unavailable"
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
        return flow, "opencv_farneback"
    except Exception:
        return None, "flow_unavailable"


def _flow_metrics(prev_gray, next_gray, cv2_mod, *, settings: dict | None = None, diff_threshold: float = 18.0) -> dict[str, float | str]:
    try:
        import numpy as np
    except Exception:
        return {
            "backend": "numpy_unavailable",
            "metrics_backend": "python_fallback",
            "flow_mean": 0.0,
            "flow_residual": 0.0,
            "flow_residual_ratio": 0.0,
            "flow_coherence": 0.0,
            "motion_jump": 0.0,
            "coherence_break": 0.0,
        }

    flow_width = max(64, min(640, _settings_int(settings, "scan_cut_visual_flow_width", 320)))
    work_prev = prev_gray
    work_next = next_gray
    try:
        h, w = prev_gray.shape[:2]
    except Exception:
        h = w = 0
    if w > flow_width > 0:
        flow_h = max(24, int(round(h * (flow_width / float(max(1, w))))))
        try:
            work_prev = cv2_mod.resize(prev_gray, (flow_width, flow_h), interpolation=cv2_mod.INTER_AREA)
            work_next = cv2_mod.resize(next_gray, (flow_width, flow_h), interpolation=cv2_mod.INTER_AREA)
        except Exception:
            work_prev = prev_gray
            work_next = next_gray

    flow, backend = _calc_flow(work_prev, work_next, cv2_mod, settings=settings)
    if flow is None:
        return {
            "backend": str(backend),
            "metrics_backend": "python_fallback",
            "flow_mean": 0.0,
            "flow_residual": 0.0,
            "flow_residual_ratio": 0.0,
            "flow_coherence": 0.0,
            "motion_jump": 0.0,
            "coherence_break": 0.0,
        }

    native_metrics = None
    if _native_dense_flow_pair_metrics is not None and _native_cut_boundary_enabled():
        native_metrics = _native_dense_flow_pair_metrics(
            work_prev,
            work_next,
            flow,
            diff_threshold=float(diff_threshold),
        )

    if isinstance(native_metrics, dict):
        diff_before = float(native_metrics.get("diff", 0.0) or 0.0)
        residual = float(native_metrics.get("residual", diff_before) or diff_before)
        residual_ratio = float(native_metrics.get("residual_ratio", residual / max(diff_before, 1e-6)) or 0.0)
        flow_mean = float(native_metrics.get("mean_motion_px", 0.0) or 0.0)
        coherence = float(native_metrics.get("coherence", 0.0) or 0.0)
        metrics_backend = "cpp_native"
    else:
        diff = np.abs(work_prev.astype(np.float32) - work_next.astype(np.float32))
        diff_before = float(diff.mean())
        fx = flow[:, :, 0].astype(np.float32)
        fy = flow[:, :, 1].astype(np.float32)
        mag = np.sqrt((fx * fx) + (fy * fy))
        flow_mean = float(mag.mean())
        mean_fx = float(fx.mean())
        mean_fy = float(fy.mean())
        coherence = float(((mean_fx * mean_fx) + (mean_fy * mean_fy)) ** 0.5 / max(flow_mean, 1e-6))
        if hasattr(cv2_mod, "remap"):
            grid_y, grid_x = np.mgrid[0:work_prev.shape[0], 0:work_prev.shape[1]].astype(np.float32)
            try:
                warped = cv2_mod.remap(
                    work_prev,
                    grid_x - fx,
                    grid_y - fy,
                    interpolation=cv2_mod.INTER_LINEAR,
                    borderMode=getattr(cv2_mod, "BORDER_REPLICATE", 1),
                )
                residual = float(np.abs(warped.astype(np.float32) - work_next.astype(np.float32)).mean())
            except Exception:
                residual = diff_before
        else:
            residual = diff_before
        residual_ratio = residual / max(diff_before, 1e-6)
        metrics_backend = "python_numpy"

    motion_jump = max(float(residual), float(flow_mean) * max(0.0, float(residual_ratio)))
    coherence_break = max(0.0, 1.0 - float(coherence)) * 100.0
    return {
        "backend": str(backend),
        "metrics_backend": str(metrics_backend),
        "flow_mean": float(flow_mean),
        "flow_residual": float(residual),
        "flow_residual_ratio": float(residual_ratio),
        "flow_coherence": float(coherence),
        "motion_jump": float(motion_jump),
        "coherence_break": float(coherence_break),
    }


def score_visual_cut_pair(
    prev_sample: dict[str, Any] | None,
    next_sample: dict[str, Any] | None,
    cv2_mod,
    *,
    settings: dict | None = None,
    region_threshold: float = 18.0,
) -> dict[str, Any]:
    empty = {
        "score": 0.0,
        "region_scores": [],
        "region_hits": 0,
        "gray_mean": 0.0,
        "pixel_ratio": 0.0,
        "edge_ratio": 0.0,
        "flow_mean": 0.0,
        "flow_residual": 0.0,
        "flow_residual_ratio": 0.0,
        "flow_coherence": 0.0,
        "motion_jump": 0.0,
        "coherence_break": 0.0,
        "hist_delta": 0.0,
        "ssim_delta": 0.0,
        "hash_delta": 0.0,
        "backend": "empty",
        "metrics_backend": "empty",
    }
    if not prev_sample or not next_sample or cv2_mod is None:
        return dict(empty)

    try:
        import numpy as np
    except Exception:
        return dict(empty)

    prev_gray = prev_sample.get("gray")
    next_gray = next_sample.get("gray")
    if prev_gray is None or next_gray is None:
        return dict(empty)
    try:
        if prev_gray.shape != next_gray.shape:
            return dict(empty)
    except Exception:
        return dict(empty)

    diff = cv2_mod.absdiff(prev_gray, next_gray)
    diff_arr = np.ascontiguousarray(diff, dtype=np.uint8)
    gray_mean = float(diff_arr.mean())
    diff_threshold = max(4.0, _settings_float(settings, "scan_cut_visual_pixel_threshold", 18.0))
    pixel_ratio = float((diff_arr >= diff_threshold).mean())

    prev_edges = prev_sample.get("edges")
    next_edges = next_sample.get("edges")
    if prev_edges is not None and next_edges is not None:
        try:
            edge_ratio = float((cv2_mod.absdiff(prev_edges, next_edges) > 0).mean())
        except Exception:
            edge_ratio = 0.0
    else:
        edge_ratio = 0.0

    mode_key = str(prev_sample.get("mode", next_sample.get("mode", "fast4")) or "fast4").lower()
    if _should_skip_flow(mode_key, gray_mean, pixel_ratio, edge_ratio, settings):
        flow_meta = {
            "backend": "edge_gray_fast_gate",
            "metrics_backend": "fast_gate_skip",
            "flow_mean": 0.0,
            "flow_residual": 0.0,
            "flow_residual_ratio": 0.0,
            "flow_coherence": 0.0,
            "motion_jump": 0.0,
            "coherence_break": 0.0,
        }
    else:
        flow_meta = _flow_metrics(prev_gray, next_gray, cv2_mod, settings=settings, diff_threshold=diff_threshold)
    motion_jump = float(flow_meta.get("motion_jump", 0.0) or 0.0)
    coherence_break = float(flow_meta.get("coherence_break", 0.0) or 0.0)
    hist_delta = _hist_delta(prev_sample.get("histogram"), next_sample.get("histogram"))
    ssim_delta = 1.0 - _ssim_lite(prev_gray, next_gray)
    hash_delta = _hash_delta(prev_sample.get("phash"), next_sample.get("phash"))

    score = (
        gray_mean * 0.48
        + (pixel_ratio * 100.0) * 0.20
        + motion_jump * 0.15
        + (edge_ratio * 100.0) * 0.04
        + coherence_break * 0.04
        + (hist_delta * 100.0) * 0.05
        + (ssim_delta * 100.0) * 0.03
        + (hash_delta * 100.0) * 0.01
    )

    height, width = prev_gray.shape[:2]
    region_scores = []
    edge_delta = cv2_mod.absdiff(prev_edges, next_edges) if prev_edges is not None and next_edges is not None else None
    for cell_x, cell_y in _mode_cells(mode_key):
        x0, x1, y0, y1 = _grid_bounds(height, width, cell_x, cell_y)
        cell_diff = diff_arr[y0:y1, x0:x1]
        if cell_diff.size <= 0:
            continue
        cell_gray = float(cell_diff.mean())
        cell_pixel = float((cell_diff >= diff_threshold).mean())
        if edge_delta is not None:
            cell_edge = float((edge_delta[y0:y1, x0:x1] > 0).mean())
        else:
            cell_edge = 0.0
        cell_score = (
            cell_gray * 0.62
            + (cell_pixel * 100.0) * 0.24
            + (cell_edge * 100.0) * 0.14
            + min(8.0, motion_jump * 0.05)
        )
        region_scores.append(float(cell_score))

    hits = sum(1 for value in region_scores if float(value) >= float(region_threshold))
    return {
        "score": float(score),
        "region_scores": [round(float(value), 4) for value in region_scores],
        "region_hits": int(hits),
        "gray_mean": round(float(gray_mean), 4),
        "pixel_ratio": round(float(pixel_ratio), 6),
        "edge_ratio": round(float(edge_ratio), 6),
        "flow_mean": round(float(flow_meta.get("flow_mean", 0.0) or 0.0), 4),
        "flow_residual": round(float(flow_meta.get("flow_residual", 0.0) or 0.0), 4),
        "flow_residual_ratio": round(float(flow_meta.get("flow_residual_ratio", 0.0) or 0.0), 4),
        "flow_coherence": round(float(flow_meta.get("flow_coherence", 0.0) or 0.0), 4),
        "motion_jump": round(float(motion_jump), 4),
        "coherence_break": round(float(coherence_break), 4),
        "hist_delta": round(float(hist_delta), 6),
        "ssim_delta": round(float(ssim_delta), 6),
        "hash_delta": round(float(hash_delta), 6),
        "backend": str(flow_meta.get("backend", "flow_unavailable") or "flow_unavailable"),
        "metrics_backend": str(flow_meta.get("metrics_backend", "python_fallback") or "python_fallback"),
    }
