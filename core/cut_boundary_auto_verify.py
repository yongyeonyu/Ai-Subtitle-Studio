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

        # color average final gate
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

        # gray 통과 조건
        gray_pass = gray_adj_pass or gray_window_pass

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

        if not gray_pass:
            return provisional_hint("gray_failed")

        if not color_pass:
            return provisional_hint("color_avg_failed")

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
        color_center = best_win["frame"] if best_win["frame"] is not None else best_adj["frame"]
        if color_center is None:
            color_center = coarse_frame
        color_lo = max(lo, int(color_center) - color_window_frames)
        color_hi = min(hi, int(color_center) + color_window_frames)
        best_color = {"frame": None, "score": -1.0, "regions": 0, "deltas": []}
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
        gray_pass = gray_adj_pass or gray_window_pass
        color_pass = best_color["frame"] is not None and best_color["score"] >= color_threshold and best_color["regions"] >= relaxed_color_required_regions
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
            "grid_cells": selected_count,
        }

    return {
        "_auto_grid_v3_manual_verify_strict": _auto_grid_v3_manual_verify_strict,
        "_auto_grid_v3_manual_verify_strict_mps": _auto_grid_v3_manual_verify_strict_mps,
    }
