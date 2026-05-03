# Version: 03.13.07
# Phase: PHASE2
"""Frame sampling and delta helpers for auto cut-boundary verification."""

from __future__ import annotations


def build_auto_grid_verify_utils(get_grid_cells):
    def _auto_gray_thumb_from_frame(frame, cv2_mod, *, positions, scale_w: int, scale_h: int):
        try:
            h, w = frame.shape[:2]
        except Exception:
            return None
        if w <= 0 or h <= 0:
            return None

        cells = get_grid_cells(w, h)
        out = []
        for idx in positions:
            try:
                x1, y1, x2, y2 = cells[int(idx)]
            except Exception:
                continue
            roi = frame[y1:y2, x1:x2]
            if roi is None or roi.size == 0:
                continue
            gray = cv2_mod.cvtColor(roi, cv2_mod.COLOR_BGR2GRAY)
            small = cv2_mod.resize(gray, (int(scale_w), int(scale_h)), interpolation=cv2_mod.INTER_AREA)
            out.append(small.tobytes())

        return tuple(out) if out else None


    def _auto_color_avg_from_frame(frame, cv2_mod, *, positions, color_space: str = "ycrcb"):
        """
        선택 grid 칸별 평균 색상 벡터를 만든다.
        YCrCb 기준:
          Y는 밝기, Cr/Cb는 색상 성분.
        """
        try:
            h, w = frame.shape[:2]
        except Exception:
            return None
        if w <= 0 or h <= 0:
            return None

        color_space = str(color_space or "ycrcb").lower()
        cells = get_grid_cells(w, h)
        out = []

        for idx in positions:
            try:
                x1, y1, x2, y2 = cells[int(idx)]
            except Exception:
                continue

            roi = frame[y1:y2, x1:x2]
            if roi is None or roi.size == 0:
                continue

            try:
                if color_space == "hsv":
                    converted = cv2_mod.cvtColor(roi, cv2_mod.COLOR_BGR2HSV)
                elif color_space == "lab":
                    converted = cv2_mod.cvtColor(roi, cv2_mod.COLOR_BGR2LAB)
                else:
                    converted = cv2_mod.cvtColor(roi, cv2_mod.COLOR_BGR2YCrCb)

                mean = converted.reshape(-1, 3).mean(axis=0)
                out.append(tuple(float(x) for x in mean))
            except Exception:
                continue

        return tuple(out) if out else None


    def _auto_delta_bytes(a: bytes, b: bytes, *, target_samples: int = 64) -> float:
        if not a or not b:
            return 0.0
        n = min(len(a), len(b))
        if n <= 0:
            return 0.0

        target_samples = max(16, min(256, int(target_samples or 64)))
        step = max(1, n // target_samples)

        total = 0
        count = 0
        for i in range(0, n, step):
            total += abs(a[i] - b[i])
            count += 1

        return total / float(count or 1)


    def _auto_gray_delta(prev_thumb, next_thumb, *, region_threshold: float, target_samples: int):
        if not prev_thumb or not next_thumb:
            return 0.0, 0, []

        n = min(len(prev_thumb), len(next_thumb))
        deltas = [
            _auto_delta_bytes(prev_thumb[i], next_thumb[i], target_samples=target_samples)
            for i in range(n)
        ]

        hits = sum(1 for d in deltas if d >= region_threshold)
        ranked = sorted(deltas, reverse=True)
        top_n = ranked[: min(3, len(ranked))]
        score = sum(top_n) / float(len(top_n) or 1)
        return float(score), int(hits), deltas


    def _auto_color_avg_delta(
        prev_avg,
        next_avg,
        *,
        threshold: float,
        weight_luma: float,
        weight_chroma: float,
    ):
        if not prev_avg or not next_avg:
            return 0.0, 0, []

        n = min(len(prev_avg), len(next_avg))
        deltas = []

        for i in range(n):
            try:
                a0, a1, a2 = prev_avg[i]
                b0, b1, b2 = next_avg[i]
                luma = abs(float(a0) - float(b0))
                chroma = (abs(float(a1) - float(b1)) + abs(float(a2) - float(b2))) / 2.0
                score = float(weight_luma) * luma + float(weight_chroma) * chroma
                deltas.append(score)
            except Exception:
                continue

        if not deltas:
            return 0.0, 0, []

        hits = sum(1 for d in deltas if d >= threshold)
        score = sum(deltas) / float(len(deltas))
        return float(score), int(hits), deltas


    def _mps_available() -> bool:
        try:
            import torch
            return bool(getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available())
        except Exception:
            return False


    def _auto_gray_delta_mps(prev_thumb, next_thumb, *, region_threshold: float, target_samples: int):
        try:
            import torch
            if not prev_thumb or not next_thumb:
                return 0.0, 0, []
            n = min(len(prev_thumb), len(next_thumb))
            deltas = []
            target_samples = max(16, min(256, int(target_samples or 64)))
            device = torch.device("mps")
            for i in range(n):
                a = prev_thumb[i]
                b = next_thumb[i]
                if not a or not b:
                    continue
                ta = torch.tensor(list(a), dtype=torch.float32, device=device)
                tb = torch.tensor(list(b), dtype=torch.float32, device=device)
                step = max(1, int(min(ta.numel(), tb.numel()) // target_samples))
                diff = torch.abs(ta[::step] - tb[::step])
                deltas.append(float(diff.mean().item()))
            if not deltas:
                return 0.0, 0, []
            hits = sum(1 for d in deltas if d >= region_threshold)
            ranked = sorted(deltas, reverse=True)
            top_n = ranked[: min(3, len(ranked))]
            score = sum(top_n) / float(len(top_n) or 1)
            return float(score), int(hits), deltas
        except Exception:
            return _auto_gray_delta(prev_thumb, next_thumb, region_threshold=region_threshold, target_samples=target_samples)


    def _auto_color_avg_delta_mps(
        prev_avg,
        next_avg,
        *,
        threshold: float,
        weight_luma: float,
        weight_chroma: float,
    ):
        try:
            import torch
            if not prev_avg or not next_avg:
                return 0.0, 0, []
            n = min(len(prev_avg), len(next_avg))
            if n <= 0:
                return 0.0, 0, []
            device = torch.device("mps")
            a = torch.tensor([list(prev_avg[i]) for i in range(n)], dtype=torch.float32, device=device)
            b = torch.tensor([list(next_avg[i]) for i in range(n)], dtype=torch.float32, device=device)
            luma = torch.abs(a[:, 0] - b[:, 0])
            chroma = (torch.abs(a[:, 1] - b[:, 1]) + torch.abs(a[:, 2] - b[:, 2])) / 2.0
            scores = (float(weight_luma) * luma) + (float(weight_chroma) * chroma)
            deltas = [float(x) for x in scores.detach().cpu().tolist()]
            hits = sum(1 for d in deltas if d >= threshold)
            score = sum(deltas) / float(len(deltas) or 1)
            return float(score), int(hits), deltas
        except Exception:
            return _auto_color_avg_delta(
                prev_avg,
                next_avg,
                threshold=threshold,
                weight_luma=weight_luma,
                weight_chroma=weight_chroma,
            )


    def _auto_capture_verify_maps(
        cap,
        cv2_mod,
        *,
        start_frame: int,
        end_frame: int,
        frame_count: int,
        positions,
        scale_w: int,
        scale_h: int,
        color_space: str,
    ):
        start_frame = max(0, int(start_frame))
        end_frame = min(int(frame_count) - 1, int(end_frame))
        if end_frame < start_frame:
            return {}, {}

        gray_map = {}
        color_map = {}

        try:
            cap.set(cv2_mod.CAP_PROP_POS_FRAMES, start_frame)
        except Exception:
            return gray_map, color_map

        f = start_frame
        while f <= end_frame:
            ok, frame = cap.read()
            if not ok or frame is None:
                break

            gray_map[f] = _auto_gray_thumb_from_frame(
                frame,
                cv2_mod,
                positions=positions,
                scale_w=scale_w,
                scale_h=scale_h,
            )
            color_map[f] = _auto_color_avg_from_frame(
                frame,
                cv2_mod,
                positions=positions,
                color_space=color_space,
            )
            f += 1

        return gray_map, color_map

    return {
        "_auto_gray_thumb_from_frame": _auto_gray_thumb_from_frame,
        "_auto_color_avg_from_frame": _auto_color_avg_from_frame,
        "_auto_delta_bytes": _auto_delta_bytes,
        "_auto_gray_delta": _auto_gray_delta,
        "_auto_color_avg_delta": _auto_color_avg_delta,
        "_mps_available": _mps_available,
        "_auto_gray_delta_mps": _auto_gray_delta_mps,
        "_auto_color_avg_delta_mps": _auto_color_avg_delta_mps,
        "_auto_capture_verify_maps": _auto_capture_verify_maps,
    }
