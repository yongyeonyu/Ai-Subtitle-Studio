# Version: 03.13.05
# Phase: PHASE2
"""Base relative scan-cut patch helpers."""

from __future__ import annotations

import os


# === SCAN CUT RELATIVE CHANGE MONKEY PATCH START ===

def _rel_scan_get_cv2_module(self):
    cv2_mod = getattr(self, "_scan_cv2_mod", None)
    if cv2_mod and cv2_mod is not False:
        return cv2_mod
    if cv2_mod is False:
        return None
    try:
        import cv2 as cv2_mod
        self._scan_cv2_mod = cv2_mod
        return cv2_mod
    except Exception as exc:
        self._scan_cv2_mod = False
        print(f"⚠️ [scan-cut-relative] OpenCV 사용 불가: {exc}", flush=True)
        return None


def _rel_scan_get_context_for_global_sec(self, global_sec: float) -> dict:
    if hasattr(self, "_resolve_active_context"):
        try:
            ctx = self._resolve_active_context(global_sec=float(global_sec))
            if isinstance(ctx, dict):
                return dict(ctx)
        except Exception:
            pass
    return {"global_sec": float(global_sec), "local_sec": float(global_sec)}


def _rel_scan_source_and_local_sec(self, global_sec: float):
    ctx = _rel_scan_get_context_for_global_sec(self, global_sec)
    source = str(ctx.get("clip_file", "") or ctx.get("source_path", "") or "")
    if not source:
        try:
            source = str(getattr(getattr(self, "video_player", None), "_current_source_path", "") or "")
        except Exception:
            source = ""
    try:
        local_sec = float(ctx.get("local_sec", global_sec) or global_sec)
    except Exception:
        local_sec = float(global_sec)
    return source, max(0.0, local_sec), ctx


def _rel_scan_get_cv2_capture(self, source_path: str):
    if not source_path or not os.path.exists(source_path):
        return None

    cv2_mod = _rel_scan_get_cv2_module(self)
    if not cv2_mod:
        return None

    norm_path = os.path.normpath(str(source_path))
    cap = getattr(self, "_scan_cv2_capture", None)
    current_path = getattr(self, "_scan_cv2_source_path", None)

    if cap is not None and current_path == norm_path:
        try:
            if cap.isOpened():
                return cap
        except Exception:
            pass

    try:
        if cap is not None:
            cap.release()
    except Exception:
        pass

    try:
        cap = cv2_mod.VideoCapture(norm_path)
        if not cap or not cap.isOpened():
            print(f"⚠️ [scan-cut-relative] VideoCapture open 실패: {norm_path}", flush=True)
            return None
        self._scan_cv2_capture = cap
        self._scan_cv2_source_path = norm_path
        return cap
    except Exception as exc:
        print(f"⚠️ [scan-cut-relative] VideoCapture 예외: {exc}", flush=True)
        return None


def _rel_scan_threshold(self) -> float:
    settings = getattr(self, "settings", {}) or {}
    try:
        return max(1.0, float(settings.get("scan_cut_threshold", 24.0)))
    except Exception:
        return 24.0


def _rel_scan_region_threshold(self) -> float:
    settings = getattr(self, "settings", {}) or {}
    try:
        return max(1.0, float(settings.get("scan_cut_region_threshold", 18.0)))
    except Exception:
        return 18.0


def _rel_scan_coarse_stride_frames(self) -> int:
    settings = getattr(self, "settings", {}) or {}
    try:
        return max(3, min(120, int(settings.get("scan_cut_relative_stride_frames", settings.get("scan_cut_coarse_stride_frames", 30)))))
    except Exception:
        return 30


def _rel_scan_rollback_frames(self) -> int:
    settings = getattr(self, "settings", {}) or {}
    try:
        return max(15, min(180, int(settings.get("scan_cut_relative_rollback_frames", settings.get("scan_cut_rollback_frames", 90)))))
    except Exception:
        return 90


def _rel_scan_refine_stages(self) -> list[int]:
    settings = getattr(self, "settings", {}) or {}
    raw = settings.get("scan_cut_relative_stages", settings.get("scan_cut_pyramid_stages", [24, 12, 6, 3, 1]))
    if isinstance(raw, str):
        try:
            out = [max(1, int(x.strip())) for x in raw.split(",") if x.strip()]
            return out or [24, 12, 6, 3, 1]
        except Exception:
            return [24, 12, 6, 3, 1]
    if isinstance(raw, (list, tuple)):
        out = []
        for x in raw:
            try:
                out.append(max(1, int(x)))
            except Exception:
                pass
        return out or [24, 12, 6, 3, 1]
    return [24, 12, 6, 3, 1]


def _rel_scan_frames_per_tick(self) -> int:
    settings = getattr(self, "settings", {}) or {}
    try:
        return max(1, min(32, int(settings.get("scan_cut_frames_per_tick", 6))))
    except Exception:
        return 6


def _rel_scan_preview_every_frames(self) -> int:
    settings = getattr(self, "settings", {}) or {}
    try:
        return max(1, min(600, int(settings.get("scan_cut_preview_every_frames", 90))))
    except Exception:
        return 90


def _rel_scan_min_delta(self) -> float:
    settings = getattr(self, "settings", {}) or {}
    try:
        return float(settings.get("scan_cut_relative_min_delta", 3.0))
    except Exception:
        return 3.0


def _rel_scan_ratio(self) -> float:
    settings = getattr(self, "settings", {}) or {}
    try:
        return float(settings.get("scan_cut_relative_ratio", 1.35))
    except Exception:
        return 1.35


def _rel_scan_prominence(self) -> float:
    settings = getattr(self, "settings", {}) or {}
    try:
        return float(settings.get("scan_cut_relative_prominence", 1.0))
    except Exception:
        return 1.0


def _rel_scan_drop_ratio(self) -> float:
    settings = getattr(self, "settings", {}) or {}
    try:
        return float(settings.get("scan_cut_relative_drop_ratio", 0.55))
    except Exception:
        return 0.55


def _rel_scan_final_min_delta(self) -> float:
    settings = getattr(self, "settings", {}) or {}
    try:
        return float(settings.get("scan_cut_relative_final_min_delta", 2.5))
    except Exception:
        return 2.5


def _rel_scan_backend_label(self) -> str:
    return "opencv-gray-relative"


def _rel_region_mode_for_stage(stage: int) -> str:
    try:
        stage = int(stage)
    except Exception:
        stage = 1
    if stage <= 1:
        return "full9"
    if stage <= 6:
        return "cross5"
    return "fast4"


def _rel_make_region_thumbnails(self, frame, cv2_mod, scale_w: int, scale_h: int, mode: str = "fast4"):
    try:
        h, w = frame.shape[:2]
    except Exception:
        return None

    if w <= 0 or h <= 0:
        return None

    xs = [0, int(w / 3), int(w * 2 / 3), w]
    ys = [0, int(h / 3), int(h * 2 / 3), h]
    mode = str(mode or "fast4").lower()

    if mode == "full9":
        cells = [
            (0, 0), (1, 0), (2, 0),
            (0, 1), (1, 1), (2, 1),
            (0, 2), (1, 2), (2, 2),
        ]
    elif mode == "cross5":
        cells = [(1, 0), (0, 1), (1, 1), (2, 1), (1, 2)]
    else:
        cells = [(1, 0), (0, 1), (2, 1), (1, 2)]

    result = []
    for cx, cy in cells:
        roi = frame[ys[cy]:ys[cy + 1], xs[cx]:xs[cx + 1]]
        if roi is None or roi.size == 0:
            return None
        gray = cv2_mod.cvtColor(roi, cv2_mod.COLOR_BGR2GRAY)
        small = cv2_mod.resize(gray, (int(scale_w), int(scale_h)), interpolation=cv2_mod.INTER_AREA)
        result.append(small.tobytes())
    return tuple(result)


def _rel_capture_image_at_global(self, global_sec: float, region_mode: str = "fast4", **_legacy_kwargs):
    cv2_mod = _rel_scan_get_cv2_module(self)
    if not cv2_mod:
        return None

    source_path, local_sec, _ctx = _rel_scan_source_and_local_sec(self, global_sec)
    if not source_path:
        return None

    cap = _rel_scan_get_cv2_capture(self, source_path)
    if cap is None:
        return None

    settings = getattr(self, "settings", {}) or {}

    try:
        scale_w = int(settings.get("scan_cut_sample_width", 18))
        scale_h = int(settings.get("scan_cut_sample_height", 10))
    except Exception:
        scale_w, scale_h = 18, 10

    scale_w = max(8, min(scale_w, 64))
    scale_h = max(6, min(scale_h, 36))

    try:
        source_fps = float(cap.get(cv2_mod.CAP_PROP_FPS) or 0.0)
    except Exception:
        source_fps = 0.0

    if source_fps <= 1.0:
        source_fps = self._current_frame_fps()

    frame_idx = max(0, int(round(float(local_sec) * source_fps)))

    try:
        current_pos = int(cap.get(cv2_mod.CAP_PROP_POS_FRAMES) or 0)
        if current_pos != frame_idx:
            cap.set(cv2_mod.CAP_PROP_POS_FRAMES, frame_idx)

        ok, frame = cap.read()
        if not ok or frame is None:
            return None

        h, w = frame.shape[:2]
        if w <= 0 or h <= 0:
            return None

        if not bool(getattr(self, "_scan_logged_relative_resolution", False)):
            self._scan_logged_relative_resolution = True
            print(
                f"🔎 [scan-cut-relative] source_resolution={w}x{h} "
                f"stride={_rel_scan_coarse_stride_frames(self)} "
                f"rollback={_rel_scan_rollback_frames(self)} "
                f"stages={_rel_scan_refine_stages(self)} "
                f"sample_each={scale_w}x{scale_h} mode=relative-change",
                flush=True,
            )

        return _rel_make_region_thumbnails(self, frame, cv2_mod, scale_w, scale_h, mode=region_mode)
    except Exception:
        return None


def _rel_delta_bytes(self, a: bytes, b: bytes) -> float:
    if not a or not b:
        return 0.0

    n = min(len(a), len(b))
    if n <= 0:
        return 0.0

    settings = getattr(self, "settings", {}) or {}
    try:
        target_samples = int(settings.get("scan_cut_target_samples", 64))
    except Exception:
        target_samples = 64

    target_samples = max(16, min(256, target_samples))
    step = max(1, n // target_samples)

    total = 0
    count = 0
    for i in range(0, n, step):
        total += abs(a[i] - b[i])
        count += 1

    return total / float(count or 1)


def _rel_region_deltas(self, prev_image, next_image):
    if not prev_image or not next_image:
        return []

    if isinstance(prev_image, (tuple, list)) and isinstance(next_image, (tuple, list)):
        n = min(len(prev_image), len(next_image))
        return [_rel_delta_bytes(self, prev_image[i], next_image[i]) for i in range(n)]

    return [_rel_delta_bytes(self, prev_image, next_image)]


def _rel_image_delta(self, prev_image, next_image) -> float:
    deltas = _rel_region_deltas(self, prev_image, next_image)
    if not deltas:
        self._scan_last_region_deltas = []
        self._scan_last_region_hits = 0
        return 0.0

    threshold = _rel_scan_region_threshold(self)
    hits = sum(1 for d in deltas if d >= threshold)
    self._scan_last_region_deltas = list(deltas)
    self._scan_last_region_hits = int(hits)

    ranked = sorted(deltas, reverse=True)

    if len(ranked) >= 9:
        top_n = ranked[:5]
    elif len(ranked) >= 5:
        top_n = ranked[:3]
    else:
        top_n = ranked[:2]

    return sum(top_n) / float(len(top_n) or 1)


def _rel_is_candidate(self, score: float, baseline: float, previous_score: float) -> tuple[bool, str]:
    abs_threshold = _rel_scan_threshold(self)
    min_delta = _rel_scan_min_delta(self)
    ratio = _rel_scan_ratio(self)
    prominence = _rel_scan_prominence(self)

    if score >= abs_threshold:
        return True, "absolute"

    if score >= min_delta and score >= max(baseline * ratio, baseline + prominence):
        return True, "relative"

    if previous_score >= min_delta and previous_score >= max(baseline * ratio, baseline + prominence):
        if score <= previous_score * _rel_scan_drop_ratio(self):
            return True, "relative_drop"

    return False, ""


def _rel_refine_boundary(self, start_frame: int, end_frame: int, fps: float, reason: str):
    try:
        fps = float(fps or self._current_frame_fps())
    except Exception:
        return None

    rollback = _rel_scan_rollback_frames(self)
    stages = _rel_scan_refine_stages(self)

    lo = max(0, min(int(start_frame), int(end_frame)) - rollback)
    hi = max(int(start_frame), int(end_frame)) + max(stages)

    best_frame = None
    best_score = -1.0
    best_regions = 0
    best_deltas = []

    for stage in stages:
        stage = max(1, int(stage))
        mode = _rel_region_mode_for_stage(stage)

        local_best_frame = None
        local_best_score = -1.0
        local_best_regions = 0
        local_best_deltas = []

        # 촘촘한 후보 탐색: stage 간격의 절반만큼 이동하면서 f -> f+stage 비교
        step = max(1, stage // 2)
        f = int(lo)
        end = max(f + 1, int(hi))

        while f < end:
            sec_a = f / fps
            sec_b = (f + stage) / fps

            img_a = _rel_capture_image_at_global(self, sec_a, region_mode=mode)
            img_b = _rel_capture_image_at_global(self, sec_b, region_mode=mode)

            if img_a is not None and img_b is not None:
                score = _rel_image_delta(self, img_a, img_b)
                regions = int(getattr(self, "_scan_last_region_hits", 0) or 0)
                deltas = list(getattr(self, "_scan_last_region_deltas", []) or [])

                if score > local_best_score:
                    local_best_frame = f
                    local_best_score = score
                    local_best_regions = regions
                    local_best_deltas = deltas

            f += step

        if local_best_frame is None:
            continue

        best_frame = int(local_best_frame)
        best_score = float(local_best_score)
        best_regions = int(local_best_regions)
        best_deltas = list(local_best_deltas)

        lo = max(0, best_frame - stage)
        hi = best_frame + stage

        delta_text = ",".join(f"{d:.1f}" for d in local_best_deltas[:9])
        print(
            f"🔍 [scan-cut-relative] REFINE stage={stage} mode={mode} "
            f"best_frame={best_frame} score={best_score:.2f} "
            f"regions={best_regions} range={lo}-{hi} deltas=[{delta_text}]",
            flush=True,
        )

    if best_frame is None:
        return None

    final_score = best_score
    final_regions = best_regions
    final_threshold = _rel_scan_final_min_delta(self)

    if final_score < final_threshold:
        print(
            f"⚠️ [scan-cut-relative] REJECT frame={best_frame} "
            f"score={final_score:.2f}/{final_threshold:.2f}",
            flush=True,
        )
        return None

    stop_frame = int(best_frame)
    stop_sec = stop_frame / fps

    delta_text = ",".join(f"{d:.1f}" for d in best_deltas[:9])
    print(
        f"🎯 [scan-cut-relative] FINAL reason={reason} "
        f"stop_frame={stop_frame} stop={stop_sec:.3f}s "
        f"score={final_score:.2f} regions={final_regions} deltas=[{delta_text}]",
        flush=True,
    )

    return stop_frame, stop_sec, final_score, final_regions, reason


def _rel_scan_cut_tick(self):
    state = getattr(self, "_scan_cut_state", None)

    if not state:
        try:
            self._scan_cut_timer.stop()
        except Exception:
            pass
        return

    if bool(state.get("busy")):
        return

    state["busy"] = True

    try:
        fps = self._current_frame_fps()
        direction = int(state.get("direction", 1) or 1)
        max_frames = int(state.get("max_frames", 0) or 0)

        frames_per_tick = _rel_scan_frames_per_tick(self)
        preview_every = _rel_scan_preview_every_frames(self)
        stride = _rel_scan_coarse_stride_frames(self)

        for _ in range(frames_per_tick):
            last_frame = max(0, int(state.get("last_frame", 0) or 0))
            next_frame = max(0, last_frame + direction * stride)
            last_sec = last_frame / fps
            next_sec = next_frame / fps
            frame_count = int(state.get("frames", 0) or 0)

            if next_frame == last_frame or (max_frames > 0 and frame_count >= max_frames):
                self._scan_cut_timer.stop()
                self._scan_cut_state = None
                self._set_scan_cut_button_active(0)
                if hasattr(self, "_scan_set_timeline_input_locked"):
                    self._scan_set_timeline_input_locked(False)
                self._scan_preview_global_sec(last_sec)
                return

            if hasattr(self, "_scan_same_source") and not self._scan_same_source(last_sec, next_sec):
                self._scan_cut_timer.stop()
                self._scan_cut_state = None
                self._set_scan_cut_button_active(0)
                if hasattr(self, "_scan_set_timeline_input_locked"):
                    self._scan_set_timeline_input_locked(False)
                self._scan_preview_global_sec(last_sec)
                print(f"🛑 [scan-cut-relative] CLIP BOUNDARY stop_frame={last_frame} stop={last_sec:.3f}s", flush=True)
                return

            # 중요: adjacent가 아니라 last_frame -> next_frame 구간 비교
            img_a = _rel_capture_image_at_global(self, last_sec, region_mode="fast4")
            img_b = _rel_capture_image_at_global(self, next_sec, region_mode="fast4")
            score = _rel_image_delta(self, img_a, img_b)

            previous_score = float(state.get("previous_score", 0.0) or 0.0)
            baseline = float(state.get("score_baseline", score) or score)

            # baseline은 변화가 천천히 반영되게 해서 sudden rise를 상대적으로 감지
            baseline_for_decision = baseline
            state["score_baseline"] = baseline * 0.90 + score * 0.10
            state["previous_score"] = score

            new_count = frame_count + stride

            if new_count == stride or (new_count // preview_every) != (frame_count // preview_every):
                self._scan_preview_global_sec(next_sec)

            is_candidate, reason = _rel_is_candidate(self, score, baseline_for_decision, previous_score)

            deltas = list(getattr(self, "_scan_last_region_deltas", []) or [])
            delta_text = ",".join(f"{d:.1f}" for d in deltas[:4])

            if new_count == stride or new_count % max(stride * 2, 1) == 0 or is_candidate:
                print(
                    f"📊 [scan-cut-relative] frame={new_count} "
                    f"delta={score:.2f} baseline={baseline_for_decision:.2f} "
                    f"prev={previous_score:.2f} stride={stride} "
                    f"reason={reason or '-'} "
                    f"frame {last_frame}->{next_frame} "
                    f"{last_sec:.3f}s->{next_sec:.3f}s "
                    f"img={_rel_scan_backend_label(self)} fast4=[{delta_text}]",
                    flush=True,
                )

            if img_a is None or img_b is None:
                self._scan_cut_timer.stop()
                self._scan_cut_state = None
                self._set_scan_cut_button_active(0)
                if hasattr(self, "_scan_set_timeline_input_locked"):
                    self._scan_set_timeline_input_locked(False)
                self._scan_preview_global_sec(last_sec)
                return

            if is_candidate:
                print(
                    f"↩️ [scan-cut-relative] RELATIVE ROLLBACK START reason={reason} "
                    f"candidate={last_frame}->{next_frame} "
                    f"{last_sec:.3f}s->{next_sec:.3f}s score={score:.2f}",
                    flush=True,
                )

                # drop 후보면 직전 구간을 더 강하게 의심
                refine_start = last_frame - stride if reason == "relative_drop" else last_frame
                refine_end = next_frame

                refined = _rel_refine_boundary(self, refine_start, refine_end, fps, reason)

                if refined:
                    stop_frame, stop_sec, final_score, final_regions, final_reason = refined

                    self._scan_cut_timer.stop()
                    self._scan_cut_state = None
                    self._set_scan_cut_button_active(0)

                    if hasattr(self, "_scan_set_timeline_input_locked"):
                        self._scan_set_timeline_input_locked(False)

                    self._scan_preview_global_sec(stop_sec)

                    try:
                        if hasattr(self, "_scan_show_cut_thumbnail"):
                            self._scan_show_cut_thumbnail(stop_sec)
                    except Exception:
                        pass

                    try:
                        if hasattr(self, "_save_cut_boundary_to_project"):
                            self._save_cut_boundary_to_project(
                                stop_sec,
                                frame=stop_frame,
                                score=final_score,
                                regions=final_regions,
                                reason=f"relative_{final_reason}",
                            )
                    except Exception as save_exc:
                        print(f"⚠️ [scan-cut-relative] project save failed: {save_exc}", flush=True)

                    print(
                        f"🛑 [scan-cut-relative] CUT FOUND reason=relative_{final_reason} "
                        f"stop_frame={stop_frame} stop={stop_sec:.3f}s "
                        f"delta={final_score:.2f} regions={final_regions}",
                        flush=True,
                    )

                    try:
                        self.video_player.info_label.setText(f"컷 경계 정지 · 상대변화 {final_score:.1f}")
                    except Exception:
                        pass

                    return

                print("↪️ [scan-cut-relative] relative rollback rejected; continue", flush=True)

            state["last_frame"] = next_frame
            state["last_image"] = img_b
            state["frames"] = new_count
            state["busy"] = False

    except Exception as exc:
        try:
            self._scan_cut_timer.stop()
        except Exception:
            pass
        self._scan_cut_state = None
        try:
            self._set_scan_cut_button_active(0)
        except Exception:
            pass
        if hasattr(self, "_scan_set_timeline_input_locked"):
            self._scan_set_timeline_input_locked(False)
        print(f"❌ [scan-cut-relative] tick error: {exc}", flush=True)
    finally:
        state = getattr(self, "_scan_cut_state", None)
        if state:
            state["busy"] = False


# 실제 클래스 메서드 강제 교체

# === SCAN CUT RELATIVE CHANGE MONKEY PATCH END ===


def install_scan_cut_relative_base(EditorTimelineVideoMixin):
    EditorTimelineVideoMixin._scan_get_cv2_module = _rel_scan_get_cv2_module
    EditorTimelineVideoMixin._scan_get_context_for_global_sec = _rel_scan_get_context_for_global_sec
    EditorTimelineVideoMixin._scan_source_and_local_sec = _rel_scan_source_and_local_sec
    EditorTimelineVideoMixin._scan_get_cv2_capture = _rel_scan_get_cv2_capture
    EditorTimelineVideoMixin._scan_threshold = _rel_scan_threshold
    EditorTimelineVideoMixin._scan_region_threshold = _rel_scan_region_threshold
    EditorTimelineVideoMixin._scan_coarse_stride_frames = _rel_scan_coarse_stride_frames
    EditorTimelineVideoMixin._scan_image_backend_label = _rel_scan_backend_label
    EditorTimelineVideoMixin._scan_make_cross_region_thumbnails = _rel_make_region_thumbnails
    EditorTimelineVideoMixin._scan_capture_image_at_global = _rel_capture_image_at_global
    EditorTimelineVideoMixin._scan_image_delta = _rel_image_delta
    EditorTimelineVideoMixin._scan_cut_tick = _rel_scan_cut_tick
