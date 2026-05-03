# Version: 03.13.05
# Phase: PHASE2
"""Relative scan-cut refinement and decision guards."""

from __future__ import annotations

from ui.editor.timeline_scan_cut_relative_base import (
    _rel_capture_image_at_global,
    _rel_image_delta,
    _rel_region_mode_for_stage,
    _rel_scan_backend_label,
    _rel_scan_coarse_stride_frames,
    _rel_scan_drop_ratio,
    _rel_scan_final_min_delta,
    _rel_scan_frames_per_tick,
    _rel_scan_min_delta,
    _rel_scan_preview_every_frames,
    _rel_scan_prominence,
    _rel_scan_ratio,
    _rel_scan_refine_stages,
    _rel_scan_rollback_frames,
)





# === SCAN CUT RELATIVE ACCEPTANCE GUARD START ===

def _rel_abs_final_threshold(self) -> float:
    settings = getattr(self, "settings", {}) or {}
    try:
        # absolute 후보는 마지막 full9가 충분히 강해야 확정한다.
        return float(settings.get("scan_cut_absolute_final_threshold", 18.0))
    except Exception:
        return 18.0


def _rel_abs_final_regions_required(self) -> int:
    settings = getattr(self, "settings", {}) or {}
    try:
        return max(0, min(9, int(settings.get("scan_cut_absolute_final_regions_required", 1))))
    except Exception:
        return 1


def _rel_final_decision_thresholds(self, reason: str):
    reason = str(reason or "")
    if reason == "absolute":
        return _rel_abs_final_threshold(self), _rel_abs_final_regions_required(self)

    # relative / relative_drop은 페이드 감지용이라 낮은 final score를 허용한다.
    return _rel_scan_final_min_delta(self), 0


def _rel_refine_boundary(self, start_frame: int, end_frame: int, fps: float, reason: str):
    """
    Relative scan-cut refine.

    수정점:
    - absolute 후보는 final full9 결과가 약하면 reject한다.
    - relative 후보만 낮은 final threshold를 허용한다.
    """
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

        # stage 간격의 절반씩 훑어서 피크를 놓치지 않게 한다.
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

    # 최종 검증은 full9, 1프레임 기준으로 다시 수행한다.
    final_img_a = _rel_capture_image_at_global(self, best_frame / fps, region_mode="full9")
    final_img_b = _rel_capture_image_at_global(self, (best_frame + 1) / fps, region_mode="full9")
    final_score = _rel_image_delta(self, final_img_a, final_img_b)
    final_regions = int(getattr(self, "_scan_last_region_hits", 0) or 0)
    final_deltas = list(getattr(self, "_scan_last_region_deltas", []) or [])

    final_threshold, final_regions_required = _rel_final_decision_thresholds(self, reason)

    if final_score < final_threshold or final_regions < final_regions_required:
        print(
            f"⚠️ [scan-cut-relative] REJECT reason={reason} frame={best_frame} "
            f"score={final_score:.2f}/{final_threshold:.2f} "
            f"regions={final_regions}/{final_regions_required}",
            flush=True,
        )
        return None

    stop_frame = int(best_frame)
    stop_sec = stop_frame / fps

    delta_text = ",".join(f"{d:.1f}" for d in final_deltas[:9])
    print(
        f"🎯 [scan-cut-relative] FINAL reason={reason} "
        f"stop_frame={stop_frame} stop={stop_sec:.3f}s "
        f"score={final_score:.2f} regions={final_regions}/{final_regions_required} "
        f"deltas=[{delta_text}]",
        flush=True,
    )

    return stop_frame, stop_sec, final_score, final_regions, reason

# 기존 _rel_scan_cut_tick은 전역 _rel_refine_boundary 이름을 런타임에 참조하므로,
# 여기서 같은 이름을 다시 정의하면 다음 호출부터 이 안전판이 적용된다.

# === SCAN CUT RELATIVE ACCEPTANCE GUARD END ===


# === SCAN CUT RELATIVE SENSITIVITY PATCH START ===

def _rel_ignore_initial_seconds(self) -> float:
    settings = getattr(self, "settings", {}) or {}
    try:
        return float(settings.get("scan_cut_ignore_initial_seconds", 3.0))
    except Exception:
        return 3.0


def _rel_absolute_coarse_threshold(self) -> float:
    settings = getattr(self, "settings", {}) or {}
    try:
        return float(settings.get("scan_cut_absolute_coarse_threshold", 40.0))
    except Exception:
        return 40.0


def _rel_absolute_coarse_regions_required(self) -> int:
    settings = getattr(self, "settings", {}) or {}
    try:
        return max(0, min(4, int(settings.get("scan_cut_absolute_coarse_regions_required", 2))))
    except Exception:
        return 2


def _rel_recent_reject_window_frames(self) -> int:
    settings = getattr(self, "settings", {}) or {}
    try:
        return max(1, int(settings.get("scan_cut_recent_reject_window_frames", 90)))
    except Exception:
        return 90


def _rel_is_recently_rejected(self, frame: int) -> bool:
    rejected = list(getattr(self, "_scan_relative_rejected_frames", []) or [])
    window = _rel_recent_reject_window_frames(self)
    try:
        frame = int(frame)
    except Exception:
        return False
    return any(abs(frame - int(item)) <= window for item in rejected)


def _rel_mark_rejected(self, frame: int) -> None:
    rejected = list(getattr(self, "_scan_relative_rejected_frames", []) or [])
    try:
        rejected.append(int(frame))
    except Exception:
        return
    self._scan_relative_rejected_frames = rejected[-12:]


def _rel_is_candidate(self, score: float, baseline: float, previous_score: float) -> tuple[bool, str]:
    """
    상대 변화량 후보 판정 v2.

    absolute:
    - coarse 구간 변화가 아주 커야 함
    - fast4 영역 hit도 일정 수 이상이어야 함

    relative:
    - baseline 대비 충분히 튀어야 함
    - 페이드/완만 전환용
    """
    try:
        score = float(score)
        baseline = float(baseline)
        previous_score = float(previous_score)
    except Exception:
        return False, ""

    region_hits = int(getattr(self, "_scan_last_region_hits", 0) or 0)

    # hard/absolute 후보는 많이 보수적으로.
    abs_threshold = _rel_absolute_coarse_threshold(self)
    abs_regions = _rel_absolute_coarse_regions_required(self)
    if score >= abs_threshold and region_hits >= abs_regions:
        return True, "absolute"

    # relative 후보는 baseline 대비 충분히 튀어야 함.
    min_delta = _rel_scan_min_delta(self)
    ratio = _rel_scan_ratio(self)
    prominence = _rel_scan_prominence(self)

    # baseline이 너무 낮으면 ratio가 과하게 민감해지므로 floor 적용.
    baseline_floor = 4.0
    effective_baseline = max(baseline, baseline_floor)

    if score >= min_delta and score >= max(effective_baseline * ratio, effective_baseline + prominence):
        return True, "relative"

    # 변화가 확 튄 다음 떨어지는 지점도 후보로 볼 수 있지만,
    # previous_score 자체가 충분히 커야 한다.
    drop_ratio = _rel_scan_drop_ratio(self)
    if (
        previous_score >= max(min_delta * 2.0, effective_baseline * ratio)
        and score <= previous_score * drop_ratio
    ):
        return True, "relative_drop"

    return False, ""


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

            img_a = _rel_capture_image_at_global(self, last_sec, region_mode="fast4")
            img_b = _rel_capture_image_at_global(self, next_sec, region_mode="fast4")
            score = _rel_image_delta(self, img_a, img_b)

            previous_score = float(state.get("previous_score", 0.0) or 0.0)
            baseline = float(state.get("score_baseline", score) or score)

            baseline_for_decision = baseline
            state["score_baseline"] = baseline * 0.92 + score * 0.08
            state["previous_score"] = score

            new_count = frame_count + stride

            if new_count == stride or (new_count // preview_every) != (frame_count // preview_every):
                self._scan_preview_global_sec(next_sec)

            is_candidate = False
            reason = ""

            # 시작 직후는 로고/흔들림/노출 안정화가 많으므로 무시
            if last_sec >= _rel_ignore_initial_seconds(self):
                is_candidate, reason = _rel_is_candidate(self, score, baseline_for_decision, previous_score)

            # 최근 reject 주변은 반복 rollback 방지
            if is_candidate and _rel_is_recently_rejected(self, last_frame):
                is_candidate = False
                reason = "recent_reject_skip"

            deltas = list(getattr(self, "_scan_last_region_deltas", []) or [])
            region_hits = int(getattr(self, "_scan_last_region_hits", 0) or 0)
            delta_text = ",".join(f"{d:.1f}" for d in deltas[:4])

            if new_count == stride or new_count % max(stride * 2, 1) == 0 or is_candidate or reason == "recent_reject_skip":
                print(
                    f"📊 [scan-cut-relative] frame={new_count} "
                    f"delta={score:.2f} baseline={baseline_for_decision:.2f} "
                    f"prev={previous_score:.2f} regions={region_hits} stride={stride} "
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

                # reject된 주변은 다시 검사하지 않음
                _rel_mark_rejected(self, last_frame)
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


# monkey patch를 다시 고정

# === SCAN CUT RELATIVE SENSITIVITY PATCH END ===


# === SCAN CUT RELATIVE DROP GUARD START ===

def _rel_final_window_frames(self) -> int:
    settings = getattr(self, "settings", {}) or {}
    try:
        return max(2, min(60, int(settings.get("scan_cut_relative_final_window_frames", 12))))
    except Exception:
        return 12


def _rel_relative_window_threshold(self) -> float:
    settings = getattr(self, "settings", {}) or {}
    try:
        return float(settings.get("scan_cut_relative_window_threshold", 4.5))
    except Exception:
        return 4.5


def _rel_is_candidate(self, score: float, baseline: float, previous_score: float) -> tuple[bool, str]:
    """
    상대 변화량 후보 판정 v3.

    핵심:
    - relative rise는 후보로 보지 않는다.
    - peak가 나온 뒤 다음 샘플에서 확 떨어지는 relative_drop만 후보로 본다.
    - absolute는 coarse 기준을 매우 보수적으로 둔다.
    """
    try:
        score = float(score)
        baseline = float(baseline)
        previous_score = float(previous_score)
    except Exception:
        return False, ""

    region_hits = int(getattr(self, "_scan_last_region_hits", 0) or 0)

    # absolute 후보는 진짜 강한 구간만.
    abs_threshold = _rel_absolute_coarse_threshold(self)
    abs_regions = _rel_absolute_coarse_regions_required(self)
    if score >= abs_threshold and region_hits >= abs_regions:
        return True, "absolute"

    # relative는 올라가는 순간이 아니라 떨어지는 순간만 잡는다.
    min_delta = _rel_scan_min_delta(self)
    ratio = _rel_scan_ratio(self)
    prominence = _rel_scan_prominence(self)
    drop_ratio = _rel_scan_drop_ratio(self)

    baseline_floor = 2.5
    effective_baseline = max(baseline, baseline_floor)

    peak_threshold = max(
        min_delta,
        effective_baseline * ratio,
        effective_baseline + prominence,
    )

    if previous_score >= peak_threshold and score <= previous_score * drop_ratio:
        return True, "relative_drop"

    return False, ""


def _rel_refine_boundary(self, start_frame: int, end_frame: int, fps: float, reason: str):
    """
    Relative scan-cut refine v3.

    absolute:
    - 최종 1프레임 full9가 충분히 강해야 확정.

    relative_drop:
    - 최종 1프레임이 약해도 됨.
    - 대신 best_frame 주변 window full9 변화량이 충분해야 확정.
    """
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

    # absolute 후보는 1프레임 full9로 강하게 검증
    if reason == "absolute":
        final_img_a = _rel_capture_image_at_global(self, best_frame / fps, region_mode="full9")
        final_img_b = _rel_capture_image_at_global(self, (best_frame + 1) / fps, region_mode="full9")
        final_score = _rel_image_delta(self, final_img_a, final_img_b)
        final_regions = int(getattr(self, "_scan_last_region_hits", 0) or 0)
        final_deltas = list(getattr(self, "_scan_last_region_deltas", []) or [])

        final_threshold, final_regions_required = _rel_final_decision_thresholds(self, reason)

        if final_score < final_threshold or final_regions < final_regions_required:
            print(
                f"⚠️ [scan-cut-relative] REJECT reason={reason} frame={best_frame} "
                f"score={final_score:.2f}/{final_threshold:.2f} "
                f"regions={final_regions}/{final_regions_required}",
                flush=True,
            )
            return None

        stop_frame = int(best_frame)
        stop_sec = stop_frame / fps
        delta_text = ",".join(f"{d:.1f}" for d in final_deltas[:9])
        print(
            f"🎯 [scan-cut-relative] FINAL reason={reason} "
            f"stop_frame={stop_frame} stop={stop_sec:.3f}s "
            f"score={final_score:.2f} regions={final_regions}/{final_regions_required} "
            f"deltas=[{delta_text}]",
            flush=True,
        )
        return stop_frame, stop_sec, final_score, final_regions, reason

    # relative_drop 후보는 window full9로 검증
    window = _rel_final_window_frames(self)
    a_frame = max(0, int(best_frame) - window)
    b_frame = int(best_frame) + window

    win_img_a = _rel_capture_image_at_global(self, a_frame / fps, region_mode="full9")
    win_img_b = _rel_capture_image_at_global(self, b_frame / fps, region_mode="full9")
    window_score = _rel_image_delta(self, win_img_a, win_img_b)
    window_regions = int(getattr(self, "_scan_last_region_hits", 0) or 0)
    window_deltas = list(getattr(self, "_scan_last_region_deltas", []) or [])

    threshold = _rel_relative_window_threshold(self)

    if window_score < threshold:
        print(
            f"⚠️ [scan-cut-relative] REJECT reason={reason} frame={best_frame} "
            f"window_score={window_score:.2f}/{threshold:.2f} "
            f"window={a_frame}->{b_frame}",
            flush=True,
        )
        return None

    stop_frame = int(best_frame)
    stop_sec = stop_frame / fps
    delta_text = ",".join(f"{d:.1f}" for d in window_deltas[:9])

    print(
        f"🎯 [scan-cut-relative] FINAL reason={reason} "
        f"stop_frame={stop_frame} stop={stop_sec:.3f}s "
        f"window_score={window_score:.2f} regions={window_regions} "
        f"window={a_frame}->{b_frame} deltas=[{delta_text}]",
        flush=True,
    )

    return stop_frame, stop_sec, window_score, window_regions, reason


# 기존 monkey patch가 전역 _rel_is_candidate / _rel_refine_boundary 이름을 참조하므로
# 여기서 재정의하면 다음 scan부터 바로 적용된다.

# === SCAN CUT RELATIVE DROP GUARD END ===


# === SCAN CUT STRONG WINDOW PATCH START ===

def _rel_strong_window_threshold(self) -> float:
    settings = getattr(self, "settings", {}) or {}
    try:
        return float(settings.get("scan_cut_strong_window_threshold", 75.0))
    except Exception:
        return 75.0


def _rel_strong_window_regions_required(self) -> int:
    settings = getattr(self, "settings", {}) or {}
    try:
        return max(1, min(4, int(settings.get("scan_cut_strong_window_regions_required", 4))))
    except Exception:
        return 4


def _rel_is_candidate(self, score: float, baseline: float, previous_score: float) -> tuple[bool, str]:
    """
    후보 판정 v4.

    더 이상 relative_drop으로 멈추지 않는다.
    30프레임 window 변화량이 충분히 크고,
    fast4 영역 대부분이 같이 바뀔 때만 후보로 본다.
    """
    try:
        score = float(score)
    except Exception:
        return False, ""

    region_hits = int(getattr(self, "_scan_last_region_hits", 0) or 0)

    if score >= _rel_strong_window_threshold(self) and region_hits >= _rel_strong_window_regions_required(self):
        return True, "strong_window"

    return False, ""


def _rel_refine_boundary(self, start_frame: int, end_frame: int, fps: float, reason: str):
    """
    strong-window refine.

    24/12/6/3/1로 위치를 좁히되,
    최종 컷 인정 여부는 마지막 1프레임 delta가 아니라
    앞 단계 window 변화량이 충분히 강했는지로 판단한다.

    이유:
    - 페이드/디졸브는 한 프레임 delta가 작을 수 있음.
    - 33초 전환처럼 30프레임 window score가 90 이상이면 컷 후보로 인정해야 함.
    """
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

    strongest_window_score = -1.0
    strongest_window_regions = 0

    for stage in stages:
        stage = max(1, int(stage))
        mode = _rel_region_mode_for_stage(stage)

        local_best_frame = None
        local_best_score = -1.0
        local_best_regions = 0
        local_best_deltas = []

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

        # stage=1은 위치 보정용. 컷 인정 점수로 쓰지 않는다.
        if stage >= 3 and best_score > strongest_window_score:
            strongest_window_score = best_score
            strongest_window_regions = best_regions

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

    threshold = _rel_strong_window_threshold(self)
    required_regions = _rel_strong_window_regions_required(self)

    if strongest_window_score < threshold or strongest_window_regions < required_regions:
        print(
            f"⚠️ [scan-cut-relative] REJECT reason={reason} frame={best_frame} "
            f"window_score={strongest_window_score:.2f}/{threshold:.2f} "
            f"regions={strongest_window_regions}/{required_regions}",
            flush=True,
        )
        return None

    stop_frame = int(best_frame)
    stop_sec = stop_frame / fps

    delta_text = ",".join(f"{d:.1f}" for d in best_deltas[:9])
    print(
        f"🎯 [scan-cut-relative] FINAL reason=strong_window "
        f"stop_frame={stop_frame} stop={stop_sec:.3f}s "
        f"window_score={strongest_window_score:.2f} "
        f"regions={strongest_window_regions}/{required_regions} "
        f"last_score={best_score:.2f} deltas=[{delta_text}]",
        flush=True,
    )

    return stop_frame, stop_sec, strongest_window_score, strongest_window_regions, "strong_window"


# 기존 _rel_scan_cut_tick은 전역 _rel_is_candidate / _rel_refine_boundary 이름을 런타임에 참조하므로
# 여기서 재정의하면 다음 실행부터 바로 적용된다.

# === SCAN CUT STRONG WINDOW PATCH END ===


def install_scan_cut_relative_refinements(EditorTimelineVideoMixin):
    EditorTimelineVideoMixin._scan_cut_tick = _rel_scan_cut_tick
