from __future__ import annotations

"""Deterministic candidate-selection strategies for strict cut verification."""

from dataclasses import dataclass


@dataclass(frozen=True)
class StrictVerifyCandidateStrategy:
    """Own gray/color candidate ranking without UI/runtime orchestration."""

    def strict_candidate_rank(
        self,
        score: float,
        threshold: float,
        regions: int,
        required_regions: int,
        region_scale: float = 0.03,
    ) -> float:
        safe_threshold = max(1e-6, float(threshold or 0.0))
        return (float(score or 0.0) / safe_threshold) + min(int(regions or 0), int(required_regions or 1)) * float(region_scale)

    def strict_provisional_hint(self, reason: str, *, fps: float, candidates: list[dict]) -> dict:
        ranked = [dict(item) for item in list(candidates or []) if isinstance(item, dict) and item.get("frame") is not None]
        if not ranked:
            return {"passed": False, "reason": reason}
        ranked.sort(
            key=lambda item: (
                float(item.get("rank", -1.0) or -1.0),
                float(item.get("score", -1.0) or -1.0),
                int(item.get("regions", 0) or 0),
            ),
            reverse=True,
        )
        best = ranked[0]
        frame = int(best.get("frame") or 0)
        return {
            "passed": False,
            "reason": reason,
            "provisional_frame": frame,
            "provisional_sec": float(frame / float(max(fps, 1.0))),
            "provisional_score": float(best.get("score", 0.0) or 0.0),
            "provisional_regions": int(best.get("regions", 0) or 0),
            "provisional_mode": str(best.get("mode", "") or ""),
            "provisional_stage": int(best.get("stage", 0) or 0),
            "provisional_deltas": list(best.get("deltas") or []),
            "rollback_relocated": True,
        }

    def _native_gray_rollback_candidates(
        self,
        gray_map: dict,
        *,
        lo: int,
        hi: int,
        read_hi: int,
        stages: list[int],
        region_threshold: float,
        target_samples: int,
        gray_required_regions: int,
        gray_1f_threshold: float,
        gray_2f_threshold: float,
        gray_window_required: int,
        gray_window_threshold: float,
        peak_bonus_scale: float,
        peak_contrast_scale: float,
        peak_sharpness_scale: float,
    ):
        try:
            from core.native_cut_boundary import (
                gray_rollback_search as native_gray_rollback_search,
                native_cut_boundary_enabled,
            )
        except Exception:
            return None
        if not native_cut_boundary_enabled():
            return None
        max_stage = max([1, *(int(stage) for stage in list(stages or [1]))])
        last_needed = min(int(read_hi), int(hi) + max(2, max_stage))
        rows = []
        for frame_no in range(int(lo), int(last_needed) + 1):
            thumb = gray_map.get(frame_no)
            if thumb is None:
                return None
            rows.append(thumb)
        return native_gray_rollback_search(
            rows,
            start_frame=int(lo),
            hi_frame=int(hi),
            stages=[int(stage) for stage in list(stages or [1])],
            region_threshold=float(region_threshold),
            target_samples=int(target_samples or 64),
            gray_required_regions=int(gray_required_regions or 1),
            gray_1f_threshold=float(gray_1f_threshold),
            gray_2f_threshold=float(gray_2f_threshold),
            gray_window_required=int(gray_window_required or 1),
            gray_window_threshold=float(gray_window_threshold),
            peak_bonus_scale=float(peak_bonus_scale),
            peak_contrast_scale=float(peak_contrast_scale),
            peak_sharpness_scale=float(peak_sharpness_scale),
        )

    def gray_rollback_candidates(
        self,
        gray_map: dict,
        *,
        lo: int,
        hi: int,
        read_hi: int,
        stages: list[int],
        region_threshold: float,
        target_samples: int,
        gray_required_regions: int,
        gray_1f_threshold: float,
        gray_2f_threshold: float,
        gray_window_required: int,
        gray_window_threshold: float,
        peak_bonus_scale: float,
        peak_contrast_scale: float,
        peak_sharpness_scale: float,
        delta_fn,
        window_mode: str,
    ):
        best_adj = {
            "frame": None,
            "score": -1.0,
            "regions": 0,
            "deltas": [],
            "mode": "1f",
            "threshold": gray_1f_threshold,
        }
        best_win = {
            "frame": None,
            "score": -1.0,
            "regions": 0,
            "deltas": [],
            "stage": 0,
            "mode": window_mode,
        }

        native_out = self._native_gray_rollback_candidates(
            gray_map,
            lo=lo,
            hi=hi,
            read_hi=read_hi,
            stages=stages,
            region_threshold=region_threshold,
            target_samples=target_samples,
            gray_required_regions=gray_required_regions,
            gray_1f_threshold=gray_1f_threshold,
            gray_2f_threshold=gray_2f_threshold,
            gray_window_required=gray_window_required,
            gray_window_threshold=gray_window_threshold,
            peak_bonus_scale=peak_bonus_scale,
            peak_contrast_scale=peak_contrast_scale,
            peak_sharpness_scale=peak_sharpness_scale,
        )
        if isinstance(native_out, dict):
            native_adj = native_out.get("best_adj")
            if isinstance(native_adj, dict) and native_adj.get("frame") is not None:
                best_adj.update(
                    {
                        "frame": int(native_adj.get("frame")),
                        "score": float(native_adj.get("score", -1.0) or -1.0),
                        "regions": int(native_adj.get("regions", 0) or 0),
                        "deltas": list(native_adj.get("deltas") or []),
                        "mode": str(native_adj.get("mode", "1f") or "1f"),
                        "threshold": float(native_adj.get("threshold", gray_1f_threshold) or gray_1f_threshold),
                    }
                )
            native_win = native_out.get("best_win")
            if isinstance(native_win, dict) and native_win.get("frame") is not None:
                best_win.update(
                    {
                        "frame": int(native_win.get("frame")),
                        "score": float(native_win.get("score", -1.0) or -1.0),
                        "regions": int(native_win.get("regions", 0) or 0),
                        "deltas": list(native_win.get("deltas") or []),
                        "stage": int(native_win.get("stage", 0) or 0),
                        "mode": window_mode,
                    }
                )
            return best_adj, best_win, True

        def consider_adj(mode, frame_no, score, regions, deltas, threshold):
            norm = self.strict_candidate_rank(score, threshold, regions, gray_required_regions)
            old_norm = self.strict_candidate_rank(best_adj["score"], best_adj["threshold"], best_adj["regions"], gray_required_regions)
            if best_adj["frame"] is None or norm > old_norm:
                best_adj.update(
                    {
                        "frame": int(frame_no),
                        "score": float(score),
                        "regions": int(regions),
                        "deltas": list(deltas or []),
                        "mode": str(mode),
                        "threshold": float(threshold),
                    }
                )

        for frame_no in range(lo, hi + 1):
            a1 = gray_map.get(frame_no)
            b1 = gray_map.get(frame_no + 1)
            if a1 is not None and b1 is not None:
                score, regions, deltas = delta_fn(a1, b1, region_threshold=region_threshold, target_samples=target_samples)
                consider_adj("1f", frame_no, score, regions, deltas, gray_1f_threshold)

            a2 = gray_map.get(frame_no)
            b2 = gray_map.get(frame_no + 2)
            if a2 is not None and b2 is not None:
                score, regions, deltas = delta_fn(a2, b2, region_threshold=region_threshold, target_samples=target_samples)
                consider_adj("2f", frame_no + 1, score, regions, deltas, gray_2f_threshold)

        cur_lo = lo
        cur_hi = hi
        for stage in stages:
            stage = max(1, int(stage))
            step = max(1, stage // 2)
            local_frame = None
            local_score = -1.0
            local_regions = 0
            local_deltas = []

            frame_no = int(cur_lo)
            while frame_no <= int(cur_hi):
                a = gray_map.get(frame_no)
                b = gray_map.get(frame_no + stage)
                if a is not None and b is not None:
                    score, regions, deltas = delta_fn(a, b, region_threshold=region_threshold, target_samples=target_samples)
                    if score > local_score:
                        local_frame = int(frame_no)
                        local_score = float(score)
                        local_regions = int(regions)
                        local_deltas = list(deltas or [])
                frame_no += step

            if local_frame is None:
                continue
            if local_score > best_win["score"]:
                best_win.update(
                    {
                        "frame": int(local_frame),
                        "score": float(local_score),
                        "regions": int(local_regions),
                        "deltas": list(local_deltas),
                        "stage": int(stage),
                        "mode": window_mode,
                    }
                )

            cur_lo = max(lo, local_frame - stage)
            cur_hi = min(hi, local_frame + stage)

        return best_adj, best_win, False

    def _native_color_window_candidate(
        self,
        color_map: dict,
        *,
        start_frame: int,
        stop_frame: int,
        window_frames: int,
        step: int,
        threshold: float,
        required_regions: int,
        weight_luma: float,
        weight_chroma: float,
    ):
        try:
            from core.native_cut_boundary import (
                color_window_search as native_color_window_search,
                native_cut_boundary_enabled,
            )
        except Exception:
            return None
        if not native_cut_boundary_enabled():
            return None
        read_stop = int(stop_frame) + int(window_frames)
        rows = []
        for frame_no in range(int(start_frame), int(read_stop) + 1):
            row = color_map.get(frame_no)
            if row is None:
                return None
            rows.append(row)
        return native_color_window_search(
            rows,
            start_frame=int(start_frame),
            stop_frame=int(stop_frame),
            window_frames=int(window_frames),
            step=int(step),
            threshold=float(threshold),
            required_regions=int(required_regions or 1),
            weight_luma=float(weight_luma),
            weight_chroma=float(weight_chroma),
        )

    def color_window_candidate(
        self,
        color_map: dict,
        *,
        start_frame: int,
        stop_frame: int,
        window_frames: int,
        step: int,
        threshold: float,
        required_regions: int,
        weight_luma: float,
        weight_chroma: float,
        delta_fn,
    ) -> dict:
        best = {"frame": None, "score": -1.0, "regions": 0, "deltas": [], "mode": "color_window", "rank": -1.0}
        native_out = self._native_color_window_candidate(
            color_map,
            start_frame=start_frame,
            stop_frame=stop_frame,
            window_frames=window_frames,
            step=step,
            threshold=threshold,
            required_regions=required_regions,
            weight_luma=weight_luma,
            weight_chroma=weight_chroma,
        )
        if isinstance(native_out, dict) and native_out.get("frame") is not None:
            best.update(
                {
                    "frame": int(native_out.get("frame")),
                    "score": float(native_out.get("score", -1.0) or -1.0),
                    "regions": int(native_out.get("regions", 0) or 0),
                    "deltas": list(native_out.get("deltas") or []),
                    "mode": "color_window",
                    "rank": float(native_out.get("rank", -1.0) or -1.0),
                }
            )
            return best

        start = int(start_frame)
        stop = int(stop_frame)
        step = max(1, int(step or 1))
        window_frames = max(1, int(window_frames or 1))

        def consider(candidate_frame: int, score: float, regions: int, deltas):
            rank = self.strict_candidate_rank(score, threshold, regions, required_regions)
            if rank > float(best["rank"]) or (abs(rank - float(best["rank"])) < 1e-6 and float(score) > float(best["score"])):
                best.update(
                    {
                        "frame": int(candidate_frame),
                        "score": float(score),
                        "regions": int(regions),
                        "deltas": list(deltas or []),
                        "mode": "color_window",
                        "rank": float(rank),
                    }
                )

        frame_no = start
        while frame_no <= stop:
            a1 = color_map.get(frame_no)
            b1 = color_map.get(frame_no + window_frames)
            if a1 is not None and b1 is not None:
                score, regions, deltas = delta_fn(
                    a1,
                    b1,
                    threshold=threshold,
                    weight_luma=weight_luma,
                    weight_chroma=weight_chroma,
                )
                consider(frame_no, score, regions, deltas)
            frame_no += step

        return best

    def best_local_color_candidate(
        self,
        color_map: dict,
        *,
        center_frame: int,
        lo: int,
        hi: int,
        radius_frames: int,
        color_threshold: float,
        color_required_regions: int,
        weight_luma: float,
        weight_chroma: float,
        delta_fn,
    ) -> dict:
        best = {"frame": None, "score": -1.0, "regions": 0, "deltas": [], "mode": "color_local", "rank": -1.0}
        radius_frames = max(1, int(radius_frames or 1))
        start = max(int(lo), int(center_frame) - radius_frames)
        stop = min(int(hi), int(center_frame) + radius_frames)

        def consider(candidate_frame: int, score: float, regions: int, deltas, *, mode: str, threshold: float):
            closeness = max(0.0, 1.0 - (abs(int(candidate_frame) - int(center_frame)) / float(max(1, radius_frames + 1))))
            rank = self.strict_candidate_rank(score, threshold, regions, color_required_regions) + (closeness * 0.08)
            if rank > float(best["rank"]) or (abs(rank - float(best["rank"])) < 1e-6 and float(score) > float(best["score"])):
                best.update(
                    {
                        "frame": int(candidate_frame),
                        "score": float(score),
                        "regions": int(regions),
                        "deltas": list(deltas or []),
                        "mode": str(mode),
                        "rank": float(rank),
                    }
                )

        for frame_no in range(start, stop + 1):
            a1 = color_map.get(frame_no)
            b1 = color_map.get(frame_no + 1)
            if a1 is not None and b1 is not None:
                score, regions, deltas = delta_fn(
                    a1,
                    b1,
                    threshold=color_threshold,
                    weight_luma=weight_luma,
                    weight_chroma=weight_chroma,
                )
                consider(frame_no, score, regions, deltas, mode="color_local_1f", threshold=color_threshold)

            a2 = color_map.get(frame_no)
            b2 = color_map.get(frame_no + 2)
            if a2 is not None and b2 is not None:
                score, regions, deltas = delta_fn(
                    a2,
                    b2,
                    threshold=color_threshold,
                    weight_luma=weight_luma,
                    weight_chroma=weight_chroma,
                )
                consider(frame_no + 1, score, regions, deltas, mode="color_local_2f", threshold=color_threshold * 1.05)

        return best

    def frame_mean_color_similarity(self, color_map: dict, *, frame: int) -> dict:
        left = color_map.get(int(frame))
        right = color_map.get(int(frame) + 1)
        if not left or not right or not isinstance(left, (list, tuple)) or not isinstance(right, (list, tuple)):
            return {"available": False, "score": 0.0, "luma_delta": 0.0, "chroma_delta": 0.0}
        n = min(len(left), len(right))
        if n <= 0:
            return {"available": False, "score": 0.0, "luma_delta": 0.0, "chroma_delta": 0.0}
        luma_total = 0.0
        chroma_total = 0.0
        used = 0
        for idx in range(n):
            try:
                a0, a1, a2 = left[idx]
                b0, b1, b2 = right[idx]
                luma = abs(float(a0) - float(b0))
                chroma = (abs(float(a1) - float(b1)) + abs(float(a2) - float(b2))) / 2.0
            except Exception:
                continue
            luma_total += luma
            chroma_total += chroma
            used += 1
        if used <= 0:
            return {"available": False, "score": 0.0, "luma_delta": 0.0, "chroma_delta": 0.0}
        luma_avg = luma_total / float(used)
        chroma_avg = chroma_total / float(used)
        return {
            "available": True,
            "score": (luma_avg * 0.25) + (chroma_avg * 0.75),
            "luma_delta": luma_avg,
            "chroma_delta": chroma_avg,
        }
