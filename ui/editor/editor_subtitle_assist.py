from __future__ import annotations

import re
import threading
import time
from typing import Any

from core.frame_time import frame_tolerance_sec, normalize_fps, normalize_segment_to_frame_grid, normalize_segments_to_frame_grid, segment_frame_bounds
from core.native_swift_timeline import apply_subtitle_magnet_via_swift
from core.personalization.runtime_personalization import personalization_settings_override_for_media
from core.runtime.logger import get_logger
from ui.editor.editor_helpers import find_segment_at


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def compute_subtitle_magnet_policy(
    settings: dict[str, Any] | None,
    *,
    runtime_override: dict[str, Any] | None = None,
) -> dict[str, float]:
    merged = dict(settings or {})
    merged.update(dict(runtime_override or {}))
    sub_gap_break_sec = max(0.1, _safe_float(merged.get("sub_gap_break_sec"), 1.5))
    word_gap_break_sec = max(0.1, _safe_float(merged.get("word_timing_gap_break_sec"), 0.65))
    lora_micro_merge_gap_sec = max(
        sub_gap_break_sec,
        _safe_float(merged.get("subtitle_lora_micro_merge_gap_sec"), 1.8),
    )
    lora_micro_merge_min_duration = max(
        _safe_float(merged.get("sub_min_duration"), 0.3),
        _safe_float(merged.get("subtitle_lora_micro_merge_min_duration"), 0.8),
    )
    split_length_threshold = max(8, int(round(_safe_float(merged.get("split_length_threshold"), 20.0))))
    deep_bridge_gap_sec = max(0.0, _safe_float(merged.get("deep_sequence_bridge_gap_sec"), 0.3))
    continuous_threshold_sec = max(
        lora_micro_merge_gap_sec,
        _safe_float(merged.get("continuous_threshold"), 2.0),
        _safe_float(merged.get("subtitle_lora_micro_merge_continuous_sec"), 3.0),
    )
    return {
        "sub_gap_break_sec": round(sub_gap_break_sec, 3),
        "word_gap_break_sec": round(word_gap_break_sec, 3),
        "lora_micro_merge_gap_sec": round(lora_micro_merge_gap_sec, 3),
        "lora_micro_merge_min_duration": round(lora_micro_merge_min_duration, 3),
        "split_length_threshold": int(split_length_threshold),
        "deep_bridge_gap_sec": round(deep_bridge_gap_sec, 3),
        "continuous_threshold_sec": round(continuous_threshold_sec, 3),
        "recommended_threshold_sec": round(lora_micro_merge_gap_sec, 3),
    }


def _boundary_blocks_merge(
    gap_start: float,
    gap_end: float,
    rows: list[Any] | None,
    *,
    slop_sec: float = 0.05,
) -> bool:
    low = min(float(gap_start), float(gap_end)) - max(0.0, float(slop_sec))
    high = max(float(gap_start), float(gap_end)) + max(0.0, float(slop_sec))
    for row in list(rows or []):
        try:
            if isinstance(row, dict):
                sec = float(row.get("timeline_sec", row.get("time", row.get("start", 0.0))) or 0.0)
            else:
                sec = float(row or 0.0)
        except Exception:
            continue
        if low <= sec <= high:
            return True
    return False


def _vad_has_intermediate_island(
    gap_start: float,
    gap_end: float,
    vad_segments: list[dict[str, Any]] | None,
    *,
    slop_sec: float = 0.05,
) -> bool:
    inner_low = min(float(gap_start), float(gap_end)) + max(0.0, float(slop_sec))
    inner_high = max(float(gap_start), float(gap_end)) - max(0.0, float(slop_sec))
    if inner_high <= inner_low:
        return False
    for row in list(vad_segments or []):
        if not isinstance(row, dict):
            continue
        start = _safe_float(row.get("start"), 0.0)
        end = max(start, _safe_float(row.get("end"), start))
        if end <= inner_low or start >= inner_high:
            continue
        return True
    return False


def _segment_char_count(seg: dict[str, Any]) -> int:
    text = str(seg.get("text", "") or "")
    return len(re.sub(r"\s+", "", text))


def _is_micro_segment(seg: dict[str, Any], policy: dict[str, float]) -> bool:
    start = _safe_float(seg.get("start"), 0.0)
    end = max(start, _safe_float(seg.get("end"), start))
    duration = max(0.0, end - start)
    min_duration = max(0.05, _safe_float(policy.get("lora_micro_merge_min_duration"), 0.8))
    floor_chars = max(2, int(round(_safe_float(policy.get("split_length_threshold"), 20.0) * 0.45)))
    return duration < min_duration or _segment_char_count(seg) <= floor_chars


def _snapshot_row(seg: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "index": int(index),
        "line": int(seg.get("line", index) or index),
        "start": round(_safe_float(seg.get("start"), 0.0), 6),
        "end": round(_safe_float(seg.get("end"), 0.0), 6),
        "text": str(seg.get("text", "") or ""),
        "spk": str(seg.get("spk", seg.get("speaker", "")) or ""),
    }


def apply_netflix_subtitle_magnet(
    segments: list[dict[str, Any]] | None,
    *,
    threshold_sec: float,
    boundary_times: list[Any] | None = None,
    provisional_boundaries: list[Any] | None = None,
    vad_segments: list[dict[str, Any]] | None = None,
    speaker_strict: bool = True,
    fps: float = 30.0,
    policy: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    normalized_fps = normalize_fps(fps)
    effective_policy = dict(policy or {})
    if not effective_policy:
        effective_policy = {
            "lora_micro_merge_gap_sec": float(threshold_sec or 0.0),
            "deep_bridge_gap_sec": 0.0,
            "lora_micro_merge_min_duration": 0.8,
            "split_length_threshold": 20,
            "continuous_threshold_sec": float(threshold_sec or 0.0),
        }
    rows = normalize_segments_to_frame_grid(
        [
            dict(seg)
            for seg in list(segments or [])
            if isinstance(seg, dict) and not bool(seg.get("is_gap"))
        ],
        normalized_fps,
        min_frames=1,
        preserve_order=False,
    )
    if len(rows) < 2:
        return rows, {"threshold_sec": round(float(threshold_sec or 0.0), 3), "closed_pairs": 0, "merged_pairs": 0, "blocked": {}, "modes": {}}

    blocked: dict[str, int] = {}
    mode_counts: dict[str, int] = {}
    closed_pairs = 0
    snapshot_before: list[dict[str, Any]] = []
    snapshot_after: list[dict[str, Any]] = []
    tolerance_sec = frame_tolerance_sec(normalized_fps, 1.0)
    lora_gap_limit = min(float(threshold_sec or 0.0), _safe_float(effective_policy.get("lora_micro_merge_gap_sec"), threshold_sec))
    deep_gap_limit = min(float(threshold_sec or 0.0), _safe_float(effective_policy.get("deep_bridge_gap_sec"), threshold_sec))

    for index in range(len(rows) - 1):
        current = rows[index]
        nxt = rows[index + 1]
        cur_start_frame, cur_end_frame = segment_frame_bounds(current, normalized_fps, min_frames=1)
        next_start_frame, next_end_frame = segment_frame_bounds(nxt, normalized_fps, min_frames=1)
        gap_frames = next_start_frame - cur_end_frame
        gap_sec = gap_frames / normalized_fps
        if gap_frames <= 0:
            continue
        if gap_sec > float(threshold_sec or 0.0) + tolerance_sec:
            blocked["threshold"] = int(blocked.get("threshold", 0) or 0) + 1
            continue
        if speaker_strict and str(current.get("spk", "") or "") != str(nxt.get("spk", "") or ""):
            blocked["speaker"] = int(blocked.get("speaker", 0) or 0) + 1
            continue
        if _boundary_blocks_merge(current.get("end", 0.0), nxt.get("start", 0.0), boundary_times, slop_sec=tolerance_sec):
            blocked["confirmed_cut"] = int(blocked.get("confirmed_cut", 0) or 0) + 1
            continue
        if _boundary_blocks_merge(current.get("end", 0.0), nxt.get("start", 0.0), provisional_boundaries, slop_sec=tolerance_sec):
            blocked["provisional_cut"] = int(blocked.get("provisional_cut", 0) or 0) + 1
            continue
        if _vad_has_intermediate_island(current.get("end", 0.0), nxt.get("start", 0.0), vad_segments, slop_sec=tolerance_sec):
            blocked["voice_boundary"] = int(blocked.get("voice_boundary", 0) or 0) + 1
            continue

        mode = None
        if gap_sec <= deep_gap_limit + tolerance_sec:
            mode = "deep_bridge"
        elif gap_sec <= lora_gap_limit + tolerance_sec and (_is_micro_segment(current, effective_policy) or _is_micro_segment(nxt, effective_policy)):
            mode = "lora_micro"
        else:
            blocked["threshold"] = int(blocked.get("threshold", 0) or 0) + 1
            continue

        snapshot_before.extend((_snapshot_row(current, index), _snapshot_row(nxt, index + 1)))
        boundary_frame = next_start_frame
        current["end"] = (boundary_frame / normalized_fps)
        current["end_frame"] = boundary_frame
        current["timeline_end_frame"] = boundary_frame
        if isinstance(current.get("frame_range"), dict):
            current["frame_range"] = {**dict(current.get("frame_range") or {}), "end": boundary_frame, "timeline_frame_rate": normalized_fps}
        rows[index] = normalize_segment_to_frame_grid(current, normalized_fps, min_frames=1)
        rows[index + 1] = normalize_segment_to_frame_grid(nxt, normalized_fps, min_frames=1)
        snapshot_after.extend((_snapshot_row(rows[index], index), _snapshot_row(rows[index + 1], index + 1)))
        closed_pairs += 1
        mode_counts[mode] = int(mode_counts.get(mode, 0) or 0) + 1

    for line, row in enumerate(rows):
        row["line"] = int(line)
    return rows, {
        "threshold_sec": round(float(threshold_sec or 0.0), 3),
        "closed_pairs": int(closed_pairs),
        "merged_pairs": int(closed_pairs),
        "blocked": blocked,
        "modes": mode_counts,
        "snapshot_before": snapshot_before,
        "snapshot_after": snapshot_after,
    }


class EditorSubtitleAssistMixin:
    def _init_subtitle_assist_state(self) -> None:
        self._repeat_segment_target_start = None
        self._repeat_segment_target_end = None
        self._repeat_segment_last_loop_at = 0.0
        self._repeat_segment_last_space_at = 0.0
        self._repeat_segment_double_space_window_sec = 0.45
        self._repeat_segment_loop_guard_sec = 0.14
        self._subtitle_runtime_override_cache: dict[str, Any] = {}
        self._subtitle_runtime_override_loaded = False
        self._subtitle_runtime_override_loading = False
        self._subtitle_runtime_override_request_key = ""
        self._subtitle_runtime_override_generation = 0

    def _subtitle_runtime_request_key(self) -> str:
        return str(getattr(self, "media_path", "") or "").strip()

    def _current_runtime_subtitle_override(self, *, allow_sync: bool = True) -> dict[str, Any]:
        media_path = self._subtitle_runtime_request_key()
        if not media_path:
            return {}
        request_key = media_path
        if (
            bool(getattr(self, "_subtitle_runtime_override_loaded", False))
            and str(getattr(self, "_subtitle_runtime_override_request_key", "") or "") == request_key
        ):
            return dict(getattr(self, "_subtitle_runtime_override_cache", {}) or {})
        if not allow_sync:
            return dict(getattr(self, "_subtitle_runtime_override_cache", {}) or {})
        try:
            override = dict(
                personalization_settings_override_for_media(
                    media_path,
                    base_settings=dict(getattr(self, "settings", {}) or {}),
                )
                or {}
            )
        except Exception:
            override = {}
        self._subtitle_runtime_override_cache = dict(override)
        self._subtitle_runtime_override_request_key = request_key
        self._subtitle_runtime_override_loaded = True
        self._subtitle_runtime_override_loading = False
        return dict(override)

    def _schedule_subtitle_assist_runtime_refresh(self, delay_ms: int = 120) -> None:
        media_path = self._subtitle_runtime_request_key()
        if not media_path:
            self._subtitle_runtime_override_cache = {}
            self._subtitle_runtime_override_loaded = True
            self._subtitle_runtime_override_loading = False
            self._subtitle_runtime_override_request_key = ""
            return
        request_key = media_path
        if (
            bool(getattr(self, "_subtitle_runtime_override_loaded", False))
            and str(getattr(self, "_subtitle_runtime_override_request_key", "") or "") == request_key
        ):
            return
        if (
            bool(getattr(self, "_subtitle_runtime_override_loading", False))
            and str(getattr(self, "_subtitle_runtime_override_request_key", "") or "") == request_key
        ):
            return

        generation = int(getattr(self, "_subtitle_runtime_override_generation", 0) or 0) + 1
        self._subtitle_runtime_override_generation = generation
        self._subtitle_runtime_override_loading = True
        self._subtitle_runtime_override_request_key = request_key

        def _start_worker() -> None:
            if int(getattr(self, "_subtitle_runtime_override_generation", 0) or 0) != generation:
                return

            def _worker() -> None:
                try:
                    override = dict(
                        personalization_settings_override_for_media(
                            media_path,
                            base_settings=dict(getattr(self, "settings", {}) or {}),
                        )
                        or {}
                    )
                except Exception:
                    override = {}
                payload = {
                    "generation": generation,
                    "request_key": request_key,
                    "override": override,
                }
                signal = getattr(self, "sig_subtitle_assist_runtime_override_ready", None)
                if signal is not None and hasattr(signal, "emit"):
                    try:
                        signal.emit(payload)
                        return
                    except Exception:
                        pass
                self._apply_subtitle_assist_runtime_override(payload)

            try:
                threading.Thread(
                    target=_worker,
                    daemon=True,
                    name="subtitle-assist-runtime-override",
                ).start()
            except Exception:
                self._subtitle_runtime_override_loading = False

        try:
            from PyQt6.QtCore import QTimer

            QTimer.singleShot(max(0, int(delay_ms)), _start_worker)
        except Exception:
            _start_worker()

    def _apply_subtitle_assist_runtime_override(self, payload: dict[str, Any] | None) -> None:
        data = dict(payload or {})
        generation = int(data.get("generation", 0) or 0)
        request_key = str(data.get("request_key", "") or "")
        if generation and generation != int(getattr(self, "_subtitle_runtime_override_generation", 0) or 0):
            return
        if request_key and request_key != self._subtitle_runtime_request_key():
            return
        self._subtitle_runtime_override_cache = dict(data.get("override") or {})
        self._subtitle_runtime_override_loaded = True
        self._subtitle_runtime_override_loading = False
        self._subtitle_runtime_override_request_key = request_key
        self._refresh_subtitle_assist_ui(allow_sync_override=False)

    def _subtitle_magnet_policy(self, *, allow_sync_override: bool = True) -> dict[str, float]:
        return compute_subtitle_magnet_policy(
            getattr(self, "settings", {}) or {},
            runtime_override=self._current_runtime_subtitle_override(allow_sync=allow_sync_override),
        )

    def _refresh_subtitle_assist_ui(self, *, allow_sync_override: bool = False) -> None:
        timeline = getattr(self, "timeline", None)
        if timeline is None:
            return
        policy = self._subtitle_magnet_policy(allow_sync_override=allow_sync_override)
        magnet_tip = (
            "LoRA/Deep 기준으로 짧은 무음 gap만 없애고 자막 경계를 붙입니다.\n"
            f"현재 기준: 기본 무음 {policy['sub_gap_break_sec']:.2f}s, "
            f"LoRA 병합 {policy['lora_micro_merge_gap_sec']:.2f}s, "
            f"Deep bridge {policy['deep_bridge_gap_sec']:.2f}s\n"
            f"적용값: Deep {policy['deep_bridge_gap_sec']:.1f}s / LoRA micro {policy['lora_micro_merge_gap_sec']:.1f}s\n"
            "텍스트를 합치지 않고, 정식 컷 경계/임시 컷 경계/중간 음성 경계는 유지합니다."
        )
        repeat_tip = (
            "체크 시 선택된 자막 세그먼트만 반복 재생합니다.\n"
            "키보드/플레이헤드 이동으로 대상을 바꾸고, 캔버스 Space 두 번으로 다음 세그먼트로 이동합니다."
        )
        lock_tip = "실수로 세그먼트 경계를 움직이지 않도록 타임라인 직접 편집을 잠급니다."
        if hasattr(timeline, "set_toolbar_tooltips"):
            timeline.set_toolbar_tooltips(
                lock_tip=lock_tip,
                magnet_tip=magnet_tip,
                repeat_tip=repeat_tip,
            )

    def _segment_repeat_enabled(self) -> bool:
        checkbox = getattr(getattr(self, "timeline", None), "repeat_chk", None)
        try:
            return bool(checkbox is not None and checkbox.isChecked())
        except RuntimeError:
            return False

    def _on_repeat_segment_toggled(self, enabled: bool) -> None:
        if not enabled:
            self._repeat_segment_target_start = None
            self._repeat_segment_target_end = None
            self._repeat_segment_last_space_at = 0.0
            return
        seg = self._selected_repeat_segment()
        if seg:
            self._remember_repeat_segment(seg)

    def _remember_repeat_segment(self, seg: dict[str, Any] | None) -> None:
        if not isinstance(seg, dict):
            self._repeat_segment_target_start = None
            self._repeat_segment_target_end = None
            return
        self._repeat_segment_target_start = float(seg.get("start", 0.0) or 0.0)
        self._repeat_segment_target_end = float(seg.get("end", self._repeat_segment_target_start) or self._repeat_segment_target_start)

    def _selected_repeat_segment(self) -> dict[str, Any] | None:
        segs = self._get_current_segments() if hasattr(self, "_get_current_segments") else []
        rows = [seg for seg in list(segs or []) if isinstance(seg, dict) and not bool(seg.get("is_gap"))]
        if not rows:
            return None
        active_sec = getattr(self, "_active_seg_start", None)
        if active_sec is not None:
            seg = find_segment_at(rows, float(active_sec), skip_gap=True)
            if isinstance(seg, dict):
                return seg
            for row in rows:
                if abs(float(row.get("start", 0.0) or 0.0) - float(active_sec)) < 0.05:
                    return row
        timeline = getattr(self, "timeline", None)
        canvas = getattr(timeline, "canvas", None) if timeline is not None else None
        playhead_sec = float(getattr(canvas, "playhead_sec", 0.0) or 0.0) if canvas is not None else 0.0
        return find_segment_at(rows, playhead_sec, skip_gap=True)

    def _toggle_video_play_with_repeat_awareness(self) -> bool:
        seg = self._selected_repeat_segment() if self._segment_repeat_enabled() else None
        was_playing = bool(self._is_video_playing()) if hasattr(self, "_is_video_playing") else False
        if seg is not None and not was_playing:
            self._seek_global_to_segment_start(seg)
        self._toggle_video_play()
        if seg is not None:
            self._remember_repeat_segment(seg)
        return True

    def _prepare_repeat_playback_start(self) -> None:
        if not self._segment_repeat_enabled():
            return
        seg = self._selected_repeat_segment()
        if not seg:
            return
        self._remember_repeat_segment(seg)
        self._seek_global_to_segment_start(seg)

    def _handle_repeat_play_pause_shortcut(self, source: str = "") -> bool:
        source = str(source or "")
        now = time.monotonic()
        if self._segment_repeat_enabled() and source in {"window_space", "canvas_space"}:
            last = float(getattr(self, "_repeat_segment_last_space_at", 0.0) or 0.0)
            if last > 0.0 and (now - last) <= float(getattr(self, "_repeat_segment_double_space_window_sec", 0.45) or 0.45):
                self._repeat_segment_last_space_at = 0.0
                self._advance_repeat_segment()
                return True
            self._repeat_segment_last_space_at = now
        return self._toggle_video_play_with_repeat_awareness()

    def _activate_segment_for_repeat(self, seg: dict[str, Any], *, autoplay: bool = False) -> bool:
        if not isinstance(seg, dict):
            return False
        was_playing = bool(self._is_video_playing()) if hasattr(self, "_is_video_playing") else False
        if was_playing:
            try:
                self.video_player.pause_video()
            except Exception:
                pass
        lock_edit = bool(self._timeline_lock_edit_enabled()) if hasattr(self, "_timeline_lock_edit_enabled") else False
        if lock_edit:
            self._active_seg_start = float(seg.get("start", 0.0) or 0.0)
            if hasattr(self, "timeline"):
                self.timeline.set_active(self._active_seg_start)
                self._reset_playhead_smoothing(self._active_seg_start)
                self.timeline.set_playhead(self._active_seg_start)
                target_center = (float(seg.get("start", 0.0) or 0.0) + float(seg.get("end", seg.get("start", 0.0)) or seg.get("start", 0.0) or 0.0)) / 2.0
                if hasattr(self.timeline, "ensure_sec_visible"):
                    self.timeline.ensure_sec_visible(target_center, smooth=True, margin_px=96)
                else:
                    self.timeline.center_to_sec(target_center, smooth=True)
        elif hasattr(self, "_sync_cursor_to_seg"):
            self._sync_cursor_to_seg(seg, ensure_visible=True, move_cursor=True, sync_playhead=True)
        self._remember_repeat_segment(seg)
        self._seek_global_to_segment_start(seg)
        if autoplay or was_playing:
            self._toggle_video_play()
        return True

    def _seek_global_to_segment_start(self, seg: dict[str, Any]) -> None:
        start_sec = float(seg.get("start", 0.0) or 0.0)
        moved = bool(self._seek_global_exact(start_sec)) if hasattr(self, "_seek_global_exact") else False
        if not moved and hasattr(self, "video_player"):
            local_sec = self._global_to_local_sec(start_sec) if hasattr(self, "_global_to_local_sec") else start_sec
            self.video_player.seek_direct(local_sec)
        if hasattr(self, "timeline"):
            self._reset_playhead_smoothing(start_sec)
            self.timeline.set_playhead(start_sec)

    def _advance_repeat_segment(self) -> bool:
        segs = [seg for seg in list(self._get_current_segments() or []) if isinstance(seg, dict) and not bool(seg.get("is_gap"))]
        if len(segs) < 2:
            return False
        current = self._selected_repeat_segment()
        if not current:
            return False
        for idx, seg in enumerate(segs):
            if abs(float(seg.get("start", 0.0) or 0.0) - float(current.get("start", 0.0) or 0.0)) < 0.05:
                next_seg = segs[min(idx + 1, len(segs) - 1)]
                if next_seg is seg:
                    return False
                return self._activate_segment_for_repeat(next_seg, autoplay=bool(self._is_video_playing()) if hasattr(self, "_is_video_playing") else False)
        return False

    def _maybe_loop_selected_segment(self, current_sec: float) -> float | None:
        if not self._segment_repeat_enabled() or not (hasattr(self, "_is_video_playing") and self._is_video_playing()):
            return None
        seg = self._selected_repeat_segment()
        if not seg:
            return None
        self._remember_repeat_segment(seg)
        start_sec = float(seg.get("start", 0.0) or 0.0)
        end_sec = float(seg.get("end", start_sec) or start_sec)
        fps = float(self._current_frame_fps()) if hasattr(self, "_current_frame_fps") else 30.0
        epsilon = max(0.04, 1.5 / max(1.0, fps))
        if float(current_sec or 0.0) + epsilon < end_sec:
            return None
        now = time.monotonic()
        if (now - float(getattr(self, "_repeat_segment_last_loop_at", 0.0) or 0.0)) <= float(getattr(self, "_repeat_segment_loop_guard_sec", 0.14) or 0.14):
            return start_sec
        self._repeat_segment_last_loop_at = now
        self._seek_global_to_segment_start(seg)
        return start_sec

    def _on_subtitle_magnet_requested(self) -> bool:
        policy = self._subtitle_magnet_policy()
        threshold_sec = float(policy.get("continuous_threshold_sec", 3.0) or 3.0)
        current = self._get_current_segments(force_rebuild=True) if hasattr(self, "_get_current_segments") else []
        timeline = getattr(self, "timeline", None)
        canvas = getattr(timeline, "canvas", None) if timeline is not None else None
        boundary_times = list(getattr(canvas, "boundary_times", []) or [])
        provisional_boundaries = list(getattr(canvas, "scan_boundary_times", []) or [])
        vad_segments = list(getattr(canvas, "vad_segments", []) or [])
        fps = float(getattr(self, "video_fps", 30.0) or 30.0)
        native_result = apply_subtitle_magnet_via_swift(
            segments=current,
            threshold_sec=threshold_sec,
            boundary_times=boundary_times,
            provisional_boundaries=provisional_boundaries,
            vad_segments=vad_segments,
            speaker_strict=True,
            fps=fps,
            policy=policy,
            strategy="extend_current",
        )
        if isinstance(native_result, dict) and isinstance(native_result.get("segments"), list):
            merged = [dict(seg) for seg in list(native_result.get("segments") or []) if isinstance(seg, dict)]
            report = dict(native_result.get("report") or {})
            if native_result.get("snapshotBefore") is not None:
                report["snapshot_before"] = list(native_result.get("snapshotBefore") or [])
            if native_result.get("snapshotAfter") is not None:
                report["snapshot_after"] = list(native_result.get("snapshotAfter") or [])
        else:
            merged, report = apply_netflix_subtitle_magnet(
                current,
                threshold_sec=threshold_sec,
                boundary_times=boundary_times,
                provisional_boundaries=provisional_boundaries,
                vad_segments=vad_segments,
                speaker_strict=True,
                fps=fps,
                policy=policy,
            )
        if report.get("closed_pairs", 0) <= 0:
            if hasattr(self, "status_lbl"):
                self.status_lbl.setText(
                    f"자막자석: 붙일 무음 gap이 없습니다 (Deep {policy['deep_bridge_gap_sec']:.1f}s / LoRA {policy['lora_micro_merge_gap_sec']:.1f}s)"
                )
            return False
        if hasattr(self, "_undo_mgr"):
            self._undo_mgr.push_immediate()
        self._last_subtitle_magnet_snapshot_before = list(report.get("snapshot_before") or [])
        self._last_subtitle_magnet_snapshot_after = list(report.get("snapshot_after") or [])
        active_sec = getattr(self, "_active_seg_start", None)
        active_after = None
        if active_sec is not None:
            active_after = find_segment_at(merged, float(active_sec), skip_gap=True)
            if active_after is None:
                for seg in merged:
                    if float(seg.get("start", 0.0) or 0.0) <= float(active_sec) <= float(seg.get("end", 0.0) or 0.0):
                        active_after = seg
                        break
        if hasattr(self, "apply_loaded_canvas_state"):
            self.apply_loaded_canvas_state(
                merged,
                preserve_view=True,
                mark_dirty=False,
                boundary_times=boundary_times,
                provisional_boundaries=provisional_boundaries,
                voice_activity_segments=list(getattr(canvas, "voice_activity_segments", []) or []),
            )
        try:
            self._autosave_requires_manual_save = True
        except Exception:
            pass
        if hasattr(self, "_mark_dirty"):
            self._mark_dirty()
        if isinstance(active_after, dict):
            self._active_seg_start = float(active_after.get("start", 0.0) or 0.0)
            if hasattr(self, "timeline"):
                self.timeline.set_active(self._active_seg_start)
        if hasattr(self, "status_lbl"):
            blocked = dict(report.get("blocked") or {})
            blocked_chunks = []
            if blocked.get("confirmed_cut"):
                blocked_chunks.append(f"정식컷 {blocked['confirmed_cut']}건 유지")
            if blocked.get("provisional_cut"):
                blocked_chunks.append(f"임시컷 {blocked['provisional_cut']}건 유지")
            if blocked.get("voice_boundary"):
                blocked_chunks.append(f"음성경계 {blocked['voice_boundary']}건 유지")
            if blocked.get("speaker"):
                blocked_chunks.append(f"화자변경 {blocked['speaker']}건 유지")
            mode_counts = dict(report.get("modes") or {})
            mode_chunks = []
            if mode_counts.get("deep_bridge"):
                mode_chunks.append(f"Deep {mode_counts['deep_bridge']}건")
            if mode_counts.get("lora_micro"):
                mode_chunks.append(f"LoRA {mode_counts['lora_micro']}건")
            suffix = " · ".join(blocked_chunks) if blocked_chunks else "경계 보존"
            prefix = " · ".join(mode_chunks) if mode_chunks else "조건 일치"
            self.status_lbl.setText(
                f"자막자석: {int(report.get('closed_pairs', 0) or 0)}개 gap 밀착 ({prefix} · {suffix} · 수동 저장 필요)"
            )
        get_logger().log(
            "[자막자석] "
            f"threshold={threshold_sec:.3f}s closed={int(report.get('closed_pairs', 0) or 0)} "
            f"modes={dict(report.get('modes') or {})} blocked={dict(report.get('blocked') or {})}"
        )
        return True
