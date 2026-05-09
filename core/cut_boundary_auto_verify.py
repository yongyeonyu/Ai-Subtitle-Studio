# Version: 03.14.29
# Phase: PHASE2
"""Strict color-average verifiers for auto cut-boundary scan."""

from __future__ import annotations


def build_strict_verify_helpers(deps: dict):
    normalize_cut_boundary_level = deps["normalize_cut_boundary_level"]
    get_level_positions = deps["get_level_positions"]
    _auto_capture_verify_maps = deps["_auto_capture_verify_maps"]
    _auto_gray_delta = deps["_auto_gray_delta"]
    _auto_color_avg_delta = deps["_auto_color_avg_delta"]
    _auto_gray_delta_mps = deps["_auto_gray_delta_mps"]
    _auto_color_avg_delta_mps = deps["_auto_color_avg_delta_mps"]
    _mps_available = deps["_mps_available"]

    def _auto_dense_flow_cut_check(
        cap,
        cv2_mod,
        *,
        frame: int,
        frame_count: int,
        settings: dict | None = None,
    ) -> dict:
        settings = settings or {}

        def _as_bool(value, default: bool = True) -> bool:
            if value is None:
                return bool(default)
            if isinstance(value, str):
                return value.strip().lower() not in {"0", "false", "off", "no", "disabled", "사용 안함", "끔"}
            return bool(value)

        if not _as_bool(settings.get("scan_cut_follower_dense_flow_enabled"), True):
            return {"passed": True, "reason": "disabled"}
        try:
            import numpy as np
        except Exception:
            return {"passed": True, "reason": "numpy_unavailable"}
        try:
            from core.native_cut_boundary import (
                dense_flow_pair_metrics as _native_dense_flow_pair_metrics,
                native_cut_boundary_enabled as _native_cut_boundary_enabled,
            )
            native_dense_metrics_enabled = bool(_native_cut_boundary_enabled())
        except Exception:
            _native_dense_flow_pair_metrics = None
            native_dense_metrics_enabled = False
        if not native_dense_metrics_enabled and not hasattr(cv2_mod, "remap"):
            return {"passed": True, "reason": "opencv_remap_unavailable"}

        frame_count = int(frame_count or 0)
        if frame_count <= 2:
            return {"passed": True, "reason": "not_enough_frames"}
        center = max(1, min(frame_count - 2, int(frame or 0)))
        radius = max(1, min(4, int(settings.get("scan_cut_dense_flow_window_radius", 2) or 2)))
        start_idx = max(0, center - radius)
        end_idx = min(frame_count - 1, center + radius)
        if end_idx - start_idx < 1:
            return {"passed": True, "reason": "not_enough_window"}
        max_width = max(120, min(640, int(settings.get("scan_cut_dense_flow_width", 320) or 320)))

        def _frame_to_gray(frame_bgr):
            if frame_bgr is None:
                return None
            try:
                h, w = frame_bgr.shape[:2]
                if w > max_width:
                    scale = max_width / float(w)
                    frame_bgr = cv2_mod.resize(
                        frame_bgr,
                        (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
                        interpolation=cv2_mod.INTER_AREA,
                    )
                gray = cv2_mod.cvtColor(frame_bgr, cv2_mod.COLOR_BGR2GRAY)
                return gray.astype(np.uint8, copy=False)
            except Exception:
                return None

        def _read_gray(index: int):
            try:
                cap.set(cv2_mod.CAP_PROP_POS_FRAMES, int(index))
                ok, frame_bgr = cap.read()
            except Exception:
                return None
            if not ok:
                return None
            return _frame_to_gray(frame_bgr)

        def _read_window_grays() -> dict[int, object]:
            out: dict[int, object] = {}
            if _as_bool(settings.get("scan_cut_dense_flow_sequential_window_decode_enabled"), True):
                try:
                    cap.set(cv2_mod.CAP_PROP_POS_FRAMES, int(start_idx))
                    for idx in range(start_idx, end_idx + 1):
                        ok, frame_bgr = cap.read()
                        if not ok:
                            break
                        gray = _frame_to_gray(frame_bgr)
                        if gray is not None:
                            out[idx] = gray
                except Exception:
                    out = {}
            if len(out) >= 2:
                return out
            return {
                idx: gray
                for idx in range(start_idx, end_idx + 1)
                if (gray := _read_gray(idx)) is not None
            }

        frames: dict[int, object] = {}
        luma: dict[int, float] = {}
        for idx, gray in _read_window_grays().items():
            frames[idx] = gray
            try:
                luma[idx] = float(gray.mean())
            except Exception:
                luma[idx] = 0.0
        ordered_indices = sorted(frames)
        if len(ordered_indices) < 2:
            return {"passed": True, "reason": "frame_unavailable"}

        diff_threshold = max(4.0, float(settings.get("scan_cut_dense_flow_diff_threshold", 18.0) or 18.0))
        min_diff = float(settings.get("scan_cut_dense_flow_min_diff", 14.0) or 14.0)
        strong_diff = float(settings.get("scan_cut_dense_flow_strong_diff", 62.0) or 62.0)
        min_motion = float(settings.get("scan_cut_dense_flow_min_motion_px", 0.8) or 0.8)
        max_motion_residual_ratio = float(settings.get("scan_cut_dense_flow_motion_residual_ratio", 0.88) or 0.88)
        motion_coherence = float(settings.get("scan_cut_dense_flow_motion_coherence", 0.64) or 0.64)
        min_coverage = float(settings.get("scan_cut_dense_flow_min_coverage", 0.08) or 0.08)
        motion_score_threshold = float(settings.get("scan_cut_dense_flow_motion_score_threshold", 0.56) or 0.56)
        votes_required = max(1, int(settings.get("scan_cut_dense_flow_motion_votes_required", 2) or 2))
        hard_cut_residual_ratio = float(settings.get("scan_cut_dense_flow_hard_cut_residual_ratio", 0.92) or 0.92)
        fade_brightness_range = float(settings.get("scan_cut_dense_flow_fade_brightness_range", 18.0) or 18.0)
        fade_motion_max = float(settings.get("scan_cut_dense_flow_fade_motion_max_px", 1.8) or 1.8)
        backend_preference = str(settings.get("scan_cut_dense_flow_backend", "dis") or "dis").strip().lower()

        def _clamp01(value: float) -> float:
            return max(0.0, min(1.0, float(value)))

        def _round(value: float) -> float:
            return round(float(value), 4)

        flow_engine = None
        if backend_preference != "farneback" and hasattr(cv2_mod, "DISOpticalFlow_create"):
            try:
                preset = getattr(cv2_mod, "DISOPTICAL_FLOW_PRESET_ULTRAFAST", 0)
                flow_engine = cv2_mod.DISOpticalFlow_create(preset)
            except Exception:
                flow_engine = None

        def _calc_flow(prev_gray, next_gray):
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
                return cv2_mod.calcOpticalFlowFarneback(
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
                ), "opencv_farneback"
            except Exception:
                return None, "flow_unavailable"

        def _pair_metrics(left_idx: int, right_idx: int, mode: str) -> dict | None:
            prev_gray = frames.get(left_idx)
            next_gray = frames.get(right_idx)
            if prev_gray is None or next_gray is None:
                return None
            try:
                if prev_gray.shape != next_gray.shape:
                    return None
            except Exception:
                return None

            flow, backend = _calc_flow(prev_gray, next_gray)
            if flow is None:
                return None

            metrics_backend = "python_numpy"
            native_metrics = None
            if _native_dense_flow_pair_metrics is not None:
                native_metrics = _native_dense_flow_pair_metrics(
                    prev_gray,
                    next_gray,
                    flow,
                    diff_threshold=diff_threshold,
                )
            if isinstance(native_metrics, dict):
                diff_before = float(native_metrics.get("diff", 0.0) or 0.0)
                coverage = float(native_metrics.get("coverage", 0.0) or 0.0)
                residual = float(native_metrics.get("residual", diff_before) or 0.0)
                residual_ratio = float(native_metrics.get("residual_ratio", residual / max(diff_before, 1e-6)) or 0.0)
                mean_mag = float(native_metrics.get("mean_motion_px", 0.0) or 0.0)
                mean_fx = float(native_metrics.get("mean_fx", 0.0) or 0.0)
                mean_fy = float(native_metrics.get("mean_fy", 0.0) or 0.0)
                coherence = float(native_metrics.get("coherence", 0.0) or 0.0)
                metrics_backend = "cpp_native"
            else:
                diff = np.abs(prev_gray.astype(np.float32) - next_gray.astype(np.float32))
                diff_before = float(diff.mean())
                coverage = float((diff >= diff_threshold).mean())
                h, w = prev_gray.shape[:2]
                grid_x, grid_y = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
                map_x = grid_x - flow[:, :, 0].astype(np.float32)
                map_y = grid_y - flow[:, :, 1].astype(np.float32)
                try:
                    warped = cv2_mod.remap(
                        prev_gray,
                        map_x,
                        map_y,
                        interpolation=cv2_mod.INTER_LINEAR,
                        borderMode=cv2_mod.BORDER_REPLICATE,
                    )
                    residual = float(np.abs(warped.astype(np.float32) - next_gray.astype(np.float32)).mean())
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
            residual_conf = _clamp01((max_motion_residual_ratio - residual_ratio) / max(max_motion_residual_ratio, 1e-6))
            diff_conf = _clamp01(diff_before / max(strong_diff, 1e-6))
            coverage_conf = _clamp01(coverage / max(min_coverage, 1e-6)) if min_coverage > 0 else _clamp01(coverage)
            motion_conf = _clamp01(mean_mag / max(min_motion * 4.0, 1e-6))
            motion_score = (
                diff_conf * 0.24
                + residual_conf * 0.30
                + _clamp01(coherence) * 0.24
                + coverage_conf * 0.12
                + motion_conf * 0.10
            )
            motion_like = (
                diff_before >= min_diff
                and diff_before < strong_diff
                and coverage >= min_coverage
                and mean_mag >= min_motion
                and coherence >= motion_coherence
                and residual_ratio <= max_motion_residual_ratio
                and motion_score >= motion_score_threshold
            )
            return {
                "left": int(left_idx),
                "right": int(right_idx),
                "mode": str(mode),
                "diff": diff_before,
                "residual": residual,
                "residual_ratio": residual_ratio,
                "coverage": coverage,
                "mean_motion_px": mean_mag,
                "coherence": coherence,
                "motion_score": motion_score,
                "motion_like": bool(motion_like),
                "backend": backend,
                "metrics_backend": metrics_backend,
            }

        pair_specs: list[tuple[int, int, str]] = []
        for left_idx, right_idx in zip(ordered_indices, ordered_indices[1:]):
            if right_idx == left_idx + 1:
                pair_specs.append((left_idx, right_idx, "adjacent"))
        if center - 1 in frames and center + 1 in frames:
            pair_specs.append((center - 1, center + 1, "center_bridge"))

        pair_metrics = [
            item for item in (_pair_metrics(left, right, mode) for left, right, mode in pair_specs)
            if item is not None
        ]
        if not pair_metrics:
            return {"passed": True, "reason": "flow_empty"}

        best_pair = max(pair_metrics, key=lambda item: (float(item["diff"]), float(item["coverage"])))
        motion_pairs = [item for item in pair_metrics if item.get("motion_like")]
        best_motion = max(pair_metrics, key=lambda item: float(item["motion_score"]))
        max_diff = max(float(item["diff"]) for item in pair_metrics)
        max_motion = max(float(item["mean_motion_px"]) for item in pair_metrics)
        avg_diff = sum(float(item["diff"]) for item in pair_metrics) / len(pair_metrics)
        avg_residual_ratio = sum(float(item["residual_ratio"]) for item in pair_metrics) / len(pair_metrics)
        avg_coverage = sum(float(item["coverage"]) for item in pair_metrics) / len(pair_metrics)
        avg_coherence = sum(float(item["coherence"]) for item in pair_metrics) / len(pair_metrics)
        avg_motion = sum(float(item["mean_motion_px"]) for item in pair_metrics) / len(pair_metrics)

        hard_cut_like = (
            max_diff >= strong_diff
            and float(best_pair["residual_ratio"]) >= hard_cut_residual_ratio
            and float(best_pair["coherence"]) < motion_coherence
        )
        luma_values = [luma[idx] for idx in ordered_indices if idx in luma]
        brightness_values = []
        for left_idx, right_idx in zip(ordered_indices, ordered_indices[1:]):
            if left_idx in luma and right_idx in luma:
                brightness_values.append(luma[right_idx] - luma[left_idx])
        brightness_range = (max(luma_values) - min(luma_values)) if luma_values else 0.0
        trend_epsilon = float(settings.get("scan_cut_dense_flow_brightness_trend_epsilon", 1.5) or 1.5)
        trend_signs = [1 if value > trend_epsilon else -1 if value < -trend_epsilon else 0 for value in brightness_values]
        nonzero_signs = [value for value in trend_signs if value != 0]
        brightness_monotonic = bool(nonzero_signs) and len(set(nonzero_signs)) <= 1
        brightness_trend_protected = (
            _as_bool(settings.get("scan_cut_dense_flow_fade_trend_protection_enabled"), True)
            and brightness_monotonic
            and brightness_range >= fade_brightness_range
            and max_motion <= fade_motion_max
        )

        motion_like = (
            len(motion_pairs) >= votes_required
            and float(best_motion["motion_score"]) >= motion_score_threshold
            and not hard_cut_like
            and not brightness_trend_protected
        )
        pair_payload = [
            {
                "left": item["left"],
                "right": item["right"],
                "mode": item["mode"],
                "diff": _round(item["diff"]),
                "residual": _round(item["residual"]),
                "residual_ratio": _round(item["residual_ratio"]),
                "coverage": _round(item["coverage"]),
                "mean_motion_px": _round(item["mean_motion_px"]),
                "coherence": _round(item["coherence"]),
                "motion_score": _round(item["motion_score"]),
                "motion_like": bool(item["motion_like"]),
                "backend": item["backend"],
                "metrics_backend": item.get("metrics_backend", "python_numpy"),
            }
            for item in pair_metrics
        ]
        backend_counts: dict[str, int] = {}
        for item in pair_metrics:
            backend = str(item.get("backend") or "unknown")
            backend_counts[backend] = backend_counts.get(backend, 0) + 1

        return {
            "passed": not motion_like,
            "reason": "dense_flow_motion_reject" if motion_like else "dense_flow_pass",
            "window": [int(start_idx), int(end_idx)],
            "center_frame": int(center),
            "pair_count": len(pair_metrics),
            "motion_votes": len(motion_pairs),
            "votes_required": int(votes_required),
            "diff": _round(best_pair["diff"]),
            "residual": _round(best_pair["residual"]),
            "residual_ratio": _round(best_pair["residual_ratio"]),
            "coverage": _round(best_pair["coverage"]),
            "mean_motion_px": _round(best_pair["mean_motion_px"]),
            "coherence": _round(best_pair["coherence"]),
            "motion_score": _round(best_motion["motion_score"]),
            "avg_diff": _round(avg_diff),
            "avg_residual_ratio": _round(avg_residual_ratio),
            "avg_coverage": _round(avg_coverage),
            "avg_coherence": _round(avg_coherence),
            "avg_motion_px": _round(avg_motion),
            "max_diff": _round(max_diff),
            "max_motion_px": _round(max_motion),
            "hard_cut_like": bool(hard_cut_like),
            "brightness_trend_protected": bool(brightness_trend_protected),
            "brightness_range": _round(brightness_range),
            "brightness_monotonic": bool(brightness_monotonic),
            "pairs": pair_payload,
            "backend_counts": backend_counts,
            "backend": "opencv_dense_optical_flow_window",
        }

    def _auto_grid_v3_manual_verify_strict(
        cap,
        cv2_mod,
        *,
        fps: float,
        frame_count: int,
        coarse_frame: int,
        settings: dict | None = None,
        scan_profile=None,
        sample_positions=None,
    ):
        """
        최종 검증:
        1. gray 1f/2f/window로 후보 위치 확인
        2. 선택 grid 칸의 색상 평균 변화량으로 최종 탈락/통과 결정
        """
        settings = settings or {}

        try:
            fps = float(fps or 30.0)
            frame_count = int(frame_count or 0)
            coarse_frame = int(coarse_frame)
        except Exception:
            return None

        if fps <= 0.0 or frame_count <= 1:
            return None

        level = normalize_cut_boundary_level((scan_profile or {}).get("level", "medium"))
        positions = get_level_positions(scan_profile, sample_positions)
        selected_count = len(positions)

        rollback_frames = int(settings.get("scan_cut_auto_verify_rollback_frames", round(fps * 1.0)))
        forward_frames = int(settings.get("scan_cut_auto_verify_forward_frames", round(fps * 1.0)))
        rollback_frames = max(2, min(240, rollback_frames))
        forward_frames = max(2, min(240, forward_frames))

        strict_multiplier = float(settings.get("scan_cut_follower_strict_multiplier", 1.08) or 1.08)
        strict_multiplier *= {"low": 1.04, "medium": 1.0, "high": 0.90}.get(level, 1.0)
        gray_1f_threshold = float(settings.get("scan_cut_auto_verify_threshold", 30.0)) * strict_multiplier
        gray_2f_threshold = gray_1f_threshold * float(settings.get("scan_cut_auto_verify_two_frame_threshold_multiplier", 1.15))
        gray_window_threshold = float(settings.get("scan_cut_auto_verify_window_threshold", 90.0)) * strict_multiplier
        gray_region_threshold = float(settings.get("scan_cut_region_threshold", 20.0))

        gray_region_bonus = int(settings.get("scan_cut_follower_strict_region_bonus", 1) or 1)
        if level == "high":
            gray_region_bonus = max(0, gray_region_bonus - 1)
        gray_required_regions = max(1, min(selected_count, int(settings.get("scan_cut_auto_verify_regions_required", max(3, round(selected_count * 0.6)))) + gray_region_bonus))
        gray_window_required = max(1, min(selected_count, int(settings.get("scan_cut_auto_verify_window_regions_required", max(3, round(selected_count * 0.7)))) + gray_region_bonus))

        color_space = str(settings.get("scan_cut_color_verify_space", "ycrcb") or "ycrcb")
        color_threshold = float(settings.get("scan_cut_color_avg_threshold", 18.0)) * strict_multiplier
        color_required_regions = max(1, min(selected_count, int(settings.get("scan_cut_color_avg_regions_required", max(2, round(selected_count * 0.45)))) + gray_region_bonus))
        color_weight_luma = float(settings.get("scan_cut_color_verify_weight_luma", 0.25))
        color_weight_chroma = float(settings.get("scan_cut_color_verify_weight_chroma", 0.75))
        color_window_frames = max(3, int(settings.get("scan_cut_color_avg_window_frames", 30)))

        scale_w = max(8, min(48, int(settings.get("scan_cut_sample_width", 18))))
        scale_h = max(6, min(27, int(settings.get("scan_cut_sample_height", 10))))
        target_samples = max(16, min(256, int(settings.get("scan_cut_target_samples", 64))))

        try:
            stages_raw = settings.get("scan_cut_auto_verify_window_stages", [30, 15, 6, 3, 1])
            if isinstance(stages_raw, str):
                stages = [max(1, int(x.strip())) for x in stages_raw.split(",") if x.strip()]
            else:
                stages = [max(1, int(x)) for x in list(stages_raw or [30, 15, 6, 3, 1])]
        except Exception:
            stages = [30, 15, 6, 3, 1]

        if 1 not in stages:
            stages.append(1)

        max_stage = max(max(stages or [1]), color_window_frames)

        lo = max(0, coarse_frame - rollback_frames)
        hi = min(frame_count - 2, coarse_frame + forward_frames)
        read_hi = min(frame_count - 1, hi + max_stage + 1)

        gray_map, color_map = _auto_capture_verify_maps(
            cap,
            cv2_mod,
            start_frame=lo,
            end_frame=read_hi,
            frame_count=frame_count,
            positions=positions,
            scale_w=scale_w,
            scale_h=scale_h,
            color_space=color_space,
            capture_gray=True,
            capture_color=False,
            settings=settings,
        )

        if not gray_map:
            return None

        # gray 1f/2f
        best_adj = {
            "frame": None,
            "score": -1.0,
            "regions": 0,
            "deltas": [],
            "mode": "1f",
            "threshold": gray_1f_threshold,
        }

        def consider_adj(mode, frame_no, score, regions, deltas, threshold):
            norm = (float(score) / float(threshold or 1.0)) + min(int(regions), gray_required_regions) * 0.03
            old_norm = (float(best_adj["score"]) / float(best_adj["threshold"] or 1.0)) + min(int(best_adj["regions"]), gray_required_regions) * 0.03
            if best_adj["frame"] is None or norm > old_norm:
                best_adj.update({
                    "frame": int(frame_no),
                    "score": float(score),
                    "regions": int(regions),
                    "deltas": list(deltas or []),
                    "mode": str(mode),
                    "threshold": float(threshold),
                })

        for f in range(lo, hi + 1):
            a1 = gray_map.get(f)
            b1 = gray_map.get(f + 1)
            if a1 is not None and b1 is not None:
                score, regions, deltas = _auto_gray_delta(
                    a1,
                    b1,
                    region_threshold=gray_region_threshold,
                    target_samples=target_samples,
                )
                consider_adj("1f", f, score, regions, deltas, gray_1f_threshold)

            a2 = gray_map.get(f)
            b2 = gray_map.get(f + 2)
            if a2 is not None and b2 is not None:
                score, regions, deltas = _auto_gray_delta(
                    a2,
                    b2,
                    region_threshold=gray_region_threshold,
                    target_samples=target_samples,
                )
                consider_adj("2f", f + 1, score, regions, deltas, gray_2f_threshold)

        # gray window rollback
        best_win = {
            "frame": None,
            "score": -1.0,
            "regions": 0,
            "deltas": [],
            "stage": 0,
        }

        cur_lo = lo
        cur_hi = hi

        for stage in stages:
            stage = max(1, int(stage))
            step = max(1, stage // 2)

            local_frame = None
            local_score = -1.0
            local_regions = 0
            local_deltas = []

            f = int(cur_lo)
            while f <= int(cur_hi):
                a = gray_map.get(f)
                b = gray_map.get(f + stage)
                if a is not None and b is not None:
                    score, regions, deltas = _auto_gray_delta(
                        a,
                        b,
                        region_threshold=gray_region_threshold,
                        target_samples=target_samples,
                    )
                    if score > local_score:
                        local_frame = int(f)
                        local_score = float(score)
                        local_regions = int(regions)
                        local_deltas = list(deltas or [])
                f += step

            if local_frame is None:
                continue

            if local_score > best_win["score"]:
                best_win.update({
                    "frame": int(local_frame),
                    "score": float(local_score),
                    "regions": int(local_regions),
                    "deltas": list(local_deltas),
                    "stage": int(stage),
                })

            cur_lo = max(lo, local_frame - stage)
            cur_hi = min(hi, local_frame + stage)

        gray_adj_pass = (
            best_adj["frame"] is not None
            and best_adj["score"] >= best_adj["threshold"]
            and best_adj["regions"] >= gray_required_regions
        )

        gray_window_pass = (
            best_win["frame"] is not None
            and best_win["score"] >= gray_window_threshold
            and best_win["regions"] >= gray_window_required
        )

        gray_pass = gray_adj_pass or gray_window_pass
        color_center = best_win["frame"] if best_win["frame"] is not None else best_adj["frame"]
        if color_center is None:
            color_center = coarse_frame

        color_lo = max(lo, int(color_center) - color_window_frames)
        color_hi = min(hi, int(color_center) + color_window_frames)
        best_color = {
            "frame": None,
            "score": -1.0,
            "regions": 0,
            "deltas": [],
        }

        if not gray_pass:
            def provisional_hint(reason: str):
                choices = []
                if best_win["frame"] is not None:
                    choices.append(("gray_window_rollback", best_win["frame"], best_win["score"], best_win["regions"], best_win["deltas"], best_win.get("stage", 0)))
                if best_adj["frame"] is not None:
                    choices.append((best_adj.get("mode", "gray_adj"), best_adj["frame"], best_adj["score"], best_adj["regions"], best_adj["deltas"], 1))
                if best_color["frame"] is not None:
                    choices.append(("color_window", best_color["frame"], best_color["score"], best_color["regions"], best_color["deltas"], color_window_frames))
                if not choices:
                    return {"passed": False, "reason": reason}
                mode, frame, score, regions, deltas, stage = choices[0]
                return {
                    "passed": False,
                    "reason": reason,
                    "provisional_frame": int(frame),
                    "provisional_sec": float(int(frame) / fps),
                    "provisional_score": float(score or 0.0),
                    "provisional_regions": int(regions or 0),
                    "provisional_mode": str(mode),
                    "provisional_stage": int(stage or 0),
                    "provisional_deltas": list(deltas or []),
                    "rollback_relocated": True,
                }

            return provisional_hint("gray_failed")

        try:
            gray_map.clear()
        except Exception:
            pass
        gray_map = {}

        color_read_hi = min(frame_count - 1, color_hi + color_window_frames)
        _, color_map = _auto_capture_verify_maps(
            cap,
            cv2_mod,
            start_frame=color_lo,
            end_frame=color_read_hi,
            frame_count=frame_count,
            positions=positions,
            scale_w=scale_w,
            scale_h=scale_h,
            color_space=color_space,
            capture_gray=False,
            capture_color=True,
            settings=settings,
        )

        step = max(1, color_window_frames // 2)
        f = color_lo
        while f <= color_hi:
            a = color_map.get(f)
            b = color_map.get(f + color_window_frames)
            if a is not None and b is not None:
                score, regions, deltas = _auto_color_avg_delta(
                    a,
                    b,
                    threshold=color_threshold,
                    weight_luma=color_weight_luma,
                    weight_chroma=color_weight_chroma,
                )
                if score > best_color["score"]:
                    best_color.update({
                        "frame": int(f),
                        "score": float(score),
                        "regions": int(regions),
                        "deltas": list(deltas or []),
                    })
            f += step

        gray_super_strong_for_color = (
            best_win["frame"] is not None
            and best_win["score"] >= float(settings.get("scan_cut_auto_gray_super_strong_threshold", 110.0))
            and best_win["regions"] >= max(1, min(selected_count, int(round(selected_count * 0.85))))
        )

        relaxed_color_required_regions = color_required_regions
        if gray_super_strong_for_color:
            relaxed_color_required_regions = max(1, color_required_regions - int(settings.get("scan_cut_color_avg_super_strong_relax_regions", 2)))

        color_pass = (
            best_color["frame"] is not None
            and best_color["score"] >= color_threshold
            and best_color["regions"] >= relaxed_color_required_regions
        )

        def provisional_hint(reason: str):
            choices = []
            if best_win["frame"] is not None:
                choices.append(("gray_window_rollback", best_win["frame"], best_win["score"], best_win["regions"], best_win["deltas"], best_win.get("stage", 0)))
            if best_adj["frame"] is not None:
                choices.append((best_adj.get("mode", "gray_adj"), best_adj["frame"], best_adj["score"], best_adj["regions"], best_adj["deltas"], 1))
            if best_color["frame"] is not None:
                choices.append(("color_window", best_color["frame"], best_color["score"], best_color["regions"], best_color["deltas"], color_window_frames))
            if not choices:
                return {"passed": False, "reason": reason}
            mode, frame, score, regions, deltas, stage = choices[0]
            return {
                "passed": False,
                "reason": reason,
                "provisional_frame": int(frame),
                "provisional_sec": float(int(frame) / fps),
                "provisional_score": float(score or 0.0),
                "provisional_regions": int(regions or 0),
                "provisional_mode": str(mode),
                "provisional_stage": int(stage or 0),
                "provisional_deltas": list(deltas or []),
                "rollback_relocated": True,
            }

        if not color_pass:
            return provisional_hint("color_avg_failed")

        try:
            color_map.clear()
        except Exception:
            pass

        flow_check = _auto_dense_flow_cut_check(
            cap,
            cv2_mod,
            frame=int(color_center if color_center is not None else coarse_frame),
            frame_count=frame_count,
            settings=settings,
        )
        if not flow_check.get("passed", True):
            return {"passed": False, "reason": "dense_flow_motion_reject", "dense_flow": dict(flow_check)}

        # 통과 위치 선택
        if gray_window_pass:
            selected_frame = int(best_win["frame"])
            selected_score = float(best_win["score"])
            selected_regions = int(best_win["regions"])
            selected_mode = "gray_window_color_avg"
            selected_deltas = list(best_win["deltas"])
        else:
            selected_frame = int(best_adj["frame"])
            selected_score = float(best_adj["score"])
            selected_regions = int(best_adj["regions"])
            selected_mode = "gray_adj_color_avg"
            selected_deltas = list(best_adj["deltas"])

        return {
            "passed": True,
            "mode": selected_mode,
            "reason": selected_mode,
            "frame": selected_frame,
            "sec": float(selected_frame / fps),
            "score": selected_score,
            "regions": selected_regions,
            "deltas": selected_deltas,
            "color_score": float(best_color["score"]),
            "color_regions": int(best_color["regions"]),
            "color_deltas": list(best_color["deltas"]),
            "dense_flow": dict(flow_check),
            "grid_cells": selected_count,
        }


    def _auto_grid_v3_manual_verify_strict_mps(
        cap,
        cv2_mod,
        *,
        fps: float,
        frame_count: int,
        coarse_frame: int,
        settings: dict | None = None,
        scan_profile=None,
        sample_positions=None,
    ):
        if not _mps_available():
            return _auto_grid_v3_manual_verify_strict(
                cap,
                cv2_mod,
                fps=fps,
                frame_count=frame_count,
                coarse_frame=coarse_frame,
                settings=settings,
                scan_profile=scan_profile,
                sample_positions=sample_positions,
            )

        settings = settings or {}
        try:
            fps = float(fps or 30.0)
            frame_count = int(frame_count or 0)
            coarse_frame = int(coarse_frame)
        except Exception:
            return None
        if fps <= 0.0 or frame_count <= 1:
            return None

        positions = get_level_positions(scan_profile, sample_positions)
        selected_count = len(positions)
        rollback_frames = max(2, min(240, int(settings.get("scan_cut_auto_verify_rollback_frames", round(fps * 1.0)))))
        forward_frames = max(2, min(240, int(settings.get("scan_cut_auto_verify_forward_frames", round(fps * 1.0)))))
        strict_multiplier = float(settings.get("scan_cut_follower_strict_multiplier", 1.08) or 1.08)
        gray_1f_threshold = float(settings.get("scan_cut_auto_verify_threshold", 30.0)) * strict_multiplier
        gray_2f_threshold = gray_1f_threshold * float(settings.get("scan_cut_auto_verify_two_frame_threshold_multiplier", 1.15))
        gray_window_threshold = float(settings.get("scan_cut_auto_verify_window_threshold", 90.0)) * strict_multiplier
        gray_region_threshold = float(settings.get("scan_cut_region_threshold", 20.0))
        gray_region_bonus = int(settings.get("scan_cut_follower_strict_region_bonus", 1) or 1)
        gray_required_regions = max(1, min(selected_count, int(settings.get("scan_cut_auto_verify_regions_required", max(3, round(selected_count * 0.6)))) + gray_region_bonus))
        gray_window_required = max(1, min(selected_count, int(settings.get("scan_cut_auto_verify_window_regions_required", max(3, round(selected_count * 0.7)))) + gray_region_bonus))
        color_space = str(settings.get("scan_cut_color_verify_space", "ycrcb") or "ycrcb")
        color_threshold = float(settings.get("scan_cut_color_avg_threshold", 18.0)) * strict_multiplier
        color_required_regions = max(1, min(selected_count, int(settings.get("scan_cut_color_avg_regions_required", max(2, round(selected_count * 0.45)))) + gray_region_bonus))
        color_weight_luma = float(settings.get("scan_cut_color_verify_weight_luma", 0.25))
        color_weight_chroma = float(settings.get("scan_cut_color_verify_weight_chroma", 0.75))
        color_window_frames = max(3, int(settings.get("scan_cut_color_avg_window_frames", 30)))
        scale_w = max(8, min(48, int(settings.get("scan_cut_sample_width", 18))))
        scale_h = max(6, min(27, int(settings.get("scan_cut_sample_height", 10))))
        target_samples = max(16, min(256, int(settings.get("scan_cut_target_samples", 64))))
        try:
            stages_raw = settings.get("scan_cut_auto_verify_window_stages", [30, 15, 6, 3, 1])
            stages = [max(1, int(x.strip())) for x in stages_raw.split(",") if x.strip()] if isinstance(stages_raw, str) else [max(1, int(x)) for x in list(stages_raw or [30, 15, 6, 3, 1])]
        except Exception:
            stages = [30, 15, 6, 3, 1]
        if 1 not in stages:
            stages.append(1)
        max_stage = max(max(stages or [1]), color_window_frames)
        lo = max(0, coarse_frame - rollback_frames)
        hi = min(frame_count - 2, coarse_frame + forward_frames)
        read_hi = min(frame_count - 1, hi + max_stage + 1)
        gray_map, color_map = _auto_capture_verify_maps(
            cap,
            cv2_mod,
            start_frame=lo,
            end_frame=read_hi,
            frame_count=frame_count,
            positions=positions,
            scale_w=scale_w,
            scale_h=scale_h,
            color_space=color_space,
            capture_gray=True,
            capture_color=False,
            settings=settings,
        )
        if not gray_map:
            return None
        best_adj = {"frame": None, "score": -1.0, "regions": 0, "deltas": [], "mode": "1f", "threshold": gray_1f_threshold}
        def consider_adj(mode, frame_no, score, regions, deltas, threshold):
            norm = (float(score) / float(threshold or 1.0)) + min(int(regions), gray_required_regions) * 0.03
            old_norm = (float(best_adj["score"]) / float(best_adj["threshold"] or 1.0)) + min(int(best_adj["regions"]), gray_required_regions) * 0.03
            if best_adj["frame"] is None or norm > old_norm:
                best_adj.update({"frame": int(frame_no), "score": float(score), "regions": int(regions), "deltas": list(deltas or []), "mode": str(mode), "threshold": float(threshold)})
        for f in range(lo, hi + 1):
            a1 = gray_map.get(f); b1 = gray_map.get(f + 1)
            if a1 is not None and b1 is not None:
                score, regions, deltas = _auto_gray_delta_mps(a1, b1, region_threshold=gray_region_threshold, target_samples=target_samples)
                consider_adj("1f", f, score, regions, deltas, gray_1f_threshold)
            a2 = gray_map.get(f); b2 = gray_map.get(f + 2)
            if a2 is not None and b2 is not None:
                score, regions, deltas = _auto_gray_delta_mps(a2, b2, region_threshold=gray_region_threshold, target_samples=target_samples)
                consider_adj("2f", f + 1, score, regions, deltas, gray_2f_threshold)
        best_win = {"frame": None, "score": -1.0, "regions": 0, "deltas": [], "stage": 0}
        cur_lo = lo; cur_hi = hi
        for stage in stages:
            stage = max(1, int(stage)); step = max(1, stage // 2)
            local_frame = None; local_score = -1.0; local_regions = 0; local_deltas = []
            f = int(cur_lo)
            while f <= int(cur_hi):
                a = gray_map.get(f); b = gray_map.get(f + stage)
                if a is not None and b is not None:
                    score, regions, deltas = _auto_gray_delta_mps(a, b, region_threshold=gray_region_threshold, target_samples=target_samples)
                    if score > local_score:
                        local_frame = int(f); local_score = float(score); local_regions = int(regions); local_deltas = list(deltas or [])
                f += step
            if local_frame is None:
                continue
            if local_score > best_win["score"]:
                best_win.update({"frame": int(local_frame), "score": float(local_score), "regions": int(local_regions), "deltas": list(local_deltas), "stage": int(stage)})
            cur_lo = max(lo, local_frame - stage); cur_hi = min(hi, local_frame + stage)
        gray_adj_pass = best_adj["frame"] is not None and best_adj["score"] >= best_adj["threshold"] and best_adj["regions"] >= gray_required_regions
        gray_window_pass = best_win["frame"] is not None and best_win["score"] >= gray_window_threshold and best_win["regions"] >= gray_window_required
        gray_pass = gray_adj_pass or gray_window_pass
        color_center = best_win["frame"] if best_win["frame"] is not None else best_adj["frame"]
        if color_center is None:
            color_center = coarse_frame
        color_lo = max(lo, int(color_center) - color_window_frames)
        color_hi = min(hi, int(color_center) + color_window_frames)
        best_color = {"frame": None, "score": -1.0, "regions": 0, "deltas": []}
        if not gray_pass:
            choices = []
            if best_win["frame"] is not None:
                choices.append(("gray_window_rollback_mps", best_win["frame"], best_win["score"], best_win["regions"], best_win["deltas"], best_win.get("stage", 0)))
            if best_adj["frame"] is not None:
                choices.append((best_adj.get("mode", "gray_adj_mps"), best_adj["frame"], best_adj["score"], best_adj["regions"], best_adj["deltas"], 1))
            if best_color["frame"] is not None:
                choices.append(("color_window_mps", best_color["frame"], best_color["score"], best_color["regions"], best_color["deltas"], color_window_frames))
            if not choices:
                return {"passed": False, "reason": "gray_failed"}
            mode, frame, score, regions, deltas, stage = choices[0]
            return {"passed": False, "reason": "gray_failed", "provisional_frame": int(frame), "provisional_sec": float(int(frame) / fps), "provisional_score": float(score or 0.0), "provisional_regions": int(regions or 0), "provisional_mode": str(mode), "provisional_stage": int(stage or 0), "provisional_deltas": list(deltas or []), "rollback_relocated": True}
        try:
            gray_map.clear()
        except Exception:
            pass
        gray_map = {}
        color_read_hi = min(frame_count - 1, color_hi + color_window_frames)
        _, color_map = _auto_capture_verify_maps(
            cap,
            cv2_mod,
            start_frame=color_lo,
            end_frame=color_read_hi,
            frame_count=frame_count,
            positions=positions,
            scale_w=scale_w,
            scale_h=scale_h,
            color_space=color_space,
            capture_gray=False,
            capture_color=True,
            settings=settings,
        )
        step = max(1, color_window_frames // 2)
        f = color_lo
        while f <= color_hi:
            a = color_map.get(f); b = color_map.get(f + color_window_frames)
            if a is not None and b is not None:
                score, regions, deltas = _auto_color_avg_delta_mps(a, b, threshold=color_threshold, weight_luma=color_weight_luma, weight_chroma=color_weight_chroma)
                if score > best_color["score"]:
                    best_color.update({"frame": int(f), "score": float(score), "regions": int(regions), "deltas": list(deltas or [])})
            f += step
        gray_super_strong_for_color = best_win["frame"] is not None and best_win["score"] >= float(settings.get("scan_cut_auto_gray_super_strong_threshold", 110.0)) and best_win["regions"] >= max(1, min(selected_count, int(round(selected_count * 0.85))))
        relaxed_color_required_regions = max(1, color_required_regions - int(settings.get("scan_cut_color_avg_super_strong_relax_regions", 2))) if gray_super_strong_for_color else color_required_regions
        color_pass = best_color["frame"] is not None and best_color["score"] >= color_threshold and best_color["regions"] >= relaxed_color_required_regions
        if not color_pass:
            choices = []
            if best_win["frame"] is not None:
                choices.append(("gray_window_rollback_mps", best_win["frame"], best_win["score"], best_win["regions"], best_win["deltas"], best_win.get("stage", 0)))
            if best_adj["frame"] is not None:
                choices.append((best_adj.get("mode", "gray_adj_mps"), best_adj["frame"], best_adj["score"], best_adj["regions"], best_adj["deltas"], 1))
            if best_color["frame"] is not None:
                choices.append(("color_window_mps", best_color["frame"], best_color["score"], best_color["regions"], best_color["deltas"], color_window_frames))
            mode, frame, score, regions, deltas, stage = choices[0]
            return {"passed": False, "reason": "color_avg_failed", "provisional_frame": int(frame), "provisional_sec": float(int(frame) / fps), "provisional_score": float(score or 0.0), "provisional_regions": int(regions or 0), "provisional_mode": str(mode), "provisional_stage": int(stage or 0), "provisional_deltas": list(deltas or []), "rollback_relocated": True}
        try:
            color_map.clear()
        except Exception:
            pass
        flow_check = _auto_dense_flow_cut_check(
            cap,
            cv2_mod,
            frame=int(color_center if color_center is not None else coarse_frame),
            frame_count=frame_count,
            settings=settings,
        )
        if not flow_check.get("passed", True):
            return {"passed": False, "reason": "dense_flow_motion_reject", "dense_flow": dict(flow_check)}
        if gray_window_pass:
            selected_frame = int(best_win["frame"]); selected_score = float(best_win["score"]); selected_regions = int(best_win["regions"]); selected_mode = "gray_window_color_avg_mps"; selected_deltas = list(best_win["deltas"])
        else:
            selected_frame = int(best_adj["frame"]); selected_score = float(best_adj["score"]); selected_regions = int(best_adj["regions"]); selected_mode = "gray_adj_color_avg_mps"; selected_deltas = list(best_adj["deltas"])
        return {
            "passed": True,
            "mode": selected_mode,
            "reason": selected_mode,
            "frame": selected_frame,
            "sec": float(selected_frame / fps),
            "score": selected_score,
            "regions": selected_regions,
            "deltas": selected_deltas,
            "color_score": float(best_color["score"]),
            "color_regions": int(best_color["regions"]),
            "color_deltas": list(best_color["deltas"]),
            "dense_flow": dict(flow_check),
            "grid_cells": selected_count,
        }

    return {
        "_auto_grid_v3_manual_verify_strict": _auto_grid_v3_manual_verify_strict,
        "_auto_grid_v3_manual_verify_strict_mps": _auto_grid_v3_manual_verify_strict_mps,
        "_auto_dense_flow_cut_check": _auto_dense_flow_cut_check,
    }
