# Version: 03.13.04
# Phase: PHASE2
"""Core scan-cut helpers for the editor timeline/video mixin."""

from __future__ import annotations

import os
from datetime import datetime
import math

from PyQt6.QtCore import QTimer

from core.cut_boundary import sync_project_cut_boundaries
from core.cut_boundary_jump import nearest_boundary_second, normalize_boundary_seconds


class EditorScanCutCoreMixin:
    def _scan_normalize_cut_boundary_level(self, value) -> str:
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
            "사용": "low",
            "on": "low",
            "true": "low",
            "1": "low",
            "enabled": "low",
            "높음": "medium",
            "high": "medium",
        }
        return aliases.get(raw, "medium")

    def _scan_cut_boundary_level(self, settings: dict | None = None, *, force_medium: bool = False) -> str:
        data = dict(settings or getattr(self, "settings", {}) or {})

        level = ""
        for key in (
            "scan_cut_boundary_level",
            "cut_boundary_level",
            "scan_cut_level",
        ):
            if key in data:
                level = self._scan_normalize_cut_boundary_level(data.get(key))
                break

        if not level:
            for key in (
                "cut_boundary_detection_enabled",
                "scan_cut_enabled",
                "scan_cut_auto_enabled",
                "cut_boundary_enabled",
            ):
                if key in data:
                    level = "medium" if bool(data.get(key)) else "off"
                    break

        if not level:
            level = "medium"

        if force_medium and level in {"off", "low"}:
            return "medium"
        return level

    def _scan_cut_manual_verify_settings(self, fps: float) -> dict:
        data = dict(getattr(self, "settings", {}) or {})

        try:
            fps = float(fps or 30.0)
        except Exception:
            fps = 30.0

        data["scan_cut_boundary_level"] = self._scan_cut_boundary_level(data, force_medium=True)
        data["scan_cut_follower_dense_flow_enabled"] = True
        data["scan_cut_follower_strict_multiplier"] = max(
            float(data.get("scan_cut_follower_strict_multiplier", 1.08) or 1.08),
            1.12,
        )
        data["scan_cut_auto_verify_threshold"] = max(
            float(data.get("scan_cut_auto_verify_threshold", 30.0) or 30.0),
            30.0,
        )
        data["scan_cut_auto_verify_window_threshold"] = max(
            float(data.get("scan_cut_auto_verify_window_threshold", 90.0) or 90.0),
            90.0,
        )
        data["scan_cut_auto_verify_regions_required"] = max(
            int(data.get("scan_cut_auto_verify_regions_required", 3) or 3),
            3,
        )
        data["scan_cut_auto_verify_window_regions_required"] = max(
            int(data.get("scan_cut_auto_verify_window_regions_required", 4) or 4),
            4,
        )
        data["scan_cut_color_avg_regions_required"] = max(
            int(data.get("scan_cut_color_avg_regions_required", 2) or 2),
            2,
        )
        data["scan_cut_auto_verify_rollback_frames"] = max(
            int(data.get("scan_cut_auto_verify_rollback_frames", round(fps * 1.0)) or round(fps * 1.0)),
            max(2, int(round(fps * 1.0))),
        )
        data["scan_cut_auto_verify_forward_frames"] = max(
            int(data.get("scan_cut_auto_verify_forward_frames", round(fps * 1.0)) or round(fps * 1.0)),
            max(2, int(round(fps * 1.0))),
        )
        return data

    def _scan_cut_strict_verify_bundle(self):
        bundle = getattr(self, "_scan_cut_strict_verify_bundle_cache", None)
        if bundle is not None:
            return None if bundle is False else bundle

        try:
            from core.cut_boundary_auto_profile import build_auto_grid_profile_helpers
            from core.cut_boundary_auto_utils import build_auto_grid_verify_utils
            from core.cut_boundary_auto_verify import build_strict_verify_helpers

            profile_helpers = build_auto_grid_profile_helpers(
                lambda settings=None: self._scan_cut_boundary_level(settings, force_medium=True)
            )
            verify_utils = build_auto_grid_verify_utils(profile_helpers["_auto_grid_cells"])
            strict_helpers = build_strict_verify_helpers(
                {
                    "normalize_cut_boundary_level": self._scan_normalize_cut_boundary_level,
                    "get_level_positions": profile_helpers["_auto_level_positions"],
                    "_auto_capture_verify_maps": verify_utils["_auto_capture_verify_maps"],
                    "_auto_gray_delta": verify_utils["_auto_gray_delta"],
                    "_auto_color_avg_delta": verify_utils["_auto_color_avg_delta"],
                    "_auto_gray_delta_mps": verify_utils["_auto_gray_delta_mps"],
                    "_auto_color_avg_delta_mps": verify_utils["_auto_color_avg_delta_mps"],
                    "_mps_available": verify_utils["_mps_available"],
                }
            )
            bundle = {
                "profile_fn": profile_helpers["cut_boundary_scan_profile"],
                "verify_fn": strict_helpers["_auto_grid_v3_manual_verify_strict_mps"],
            }
        except Exception as exc:
            bundle = False
            print(f"⚠️ [scan-cut] strict verify helper 준비 실패: {exc}", flush=True)

        self._scan_cut_strict_verify_bundle_cache = bundle
        return None if bundle is False else bundle

    def _scan_verify_cut_boundary_candidate(self, coarse_frame: int, fps: float, *, reason: str = ""):
        bundle = self._scan_cut_strict_verify_bundle()
        if not bundle:
            return None

        cv2_mod = self._scan_get_cv2_module()
        if not cv2_mod:
            return None

        try:
            fps = float(fps or self._current_frame_fps())
            coarse_frame = max(0, int(coarse_frame))
        except Exception:
            return None

        coarse_sec = float(coarse_frame) / max(fps, 1e-6)

        try:
            source_path, local_sec, _ctx = self._scan_source_and_local_sec(coarse_sec)
        except Exception:
            return None
        if not source_path:
            return None

        cap = self._scan_get_cv2_capture(source_path)
        if cap is None:
            return None

        try:
            source_fps = float(cap.get(cv2_mod.CAP_PROP_FPS) or 0.0)
        except Exception:
            source_fps = 0.0
        if source_fps <= 1.0:
            source_fps = fps

        local_frame = max(0, int(round(float(local_sec) * source_fps)))

        try:
            frame_count = int(cap.get(cv2_mod.CAP_PROP_FRAME_COUNT) or 0)
        except Exception:
            frame_count = 0
        if frame_count <= 1:
            try:
                frame_count = max(local_frame + 2, int(round(float(local_sec) * source_fps)) + 2)
            except Exception:
                frame_count = max(local_frame + 2, 2)

        settings = self._scan_cut_manual_verify_settings(source_fps)
        profile = bundle["profile_fn"](settings)

        try:
            verified = bundle["verify_fn"](
                cap,
                cv2_mod,
                fps=source_fps,
                frame_count=frame_count,
                coarse_frame=local_frame,
                settings=settings,
                scan_profile=profile,
                sample_positions=profile.get("positions"),
            )
        except Exception as exc:
            print(f"⚠️ [scan-cut] strict verify 실행 실패: {exc}", flush=True)
            return None

        if not isinstance(verified, dict):
            return None

        clip_global_offset = float(coarse_sec) - float(local_sec)

        if verified.get("passed"):
            try:
                verified_local_frame = int(verified.get("frame", local_frame) or local_frame)
                verified_local_sec = float(verified.get("sec", verified_local_frame / max(source_fps, 1e-6)) or 0.0)
            except Exception:
                return None

            global_sec = self._snap_to_frame(max(0.0, clip_global_offset + verified_local_sec))
            global_frame = max(0, int(round(global_sec * fps)))
            result = {
                "available": True,
                "passed": True,
                "frame": global_frame,
                "sec": global_sec,
                "local_frame": verified_local_frame,
                "local_sec": verified_local_sec,
                "score": float(verified.get("score", 0.0) or 0.0),
                "regions": int(verified.get("regions", 0) or 0),
                "mode": str(verified.get("mode", verified.get("reason", "strict_verify")) or "strict_verify"),
                "reason": str(verified.get("reason", verified.get("mode", "strict_verify")) or "strict_verify"),
                "color_score": float(verified.get("color_score", 0.0) or 0.0),
            }
            print(
                f"🎯 [scan-cut] STRICT VERIFY PASS reason={reason or '-'} "
                f"global={global_sec:.3f}s frame={global_frame} "
                f"local={verified_local_sec:.3f}s local_frame={verified_local_frame} "
                f"mode={result['mode']} score={result['score']:.2f} regions={result['regions']}",
                flush=True,
            )
            return result

        result = {
            "available": True,
            "passed": False,
            "reason": str(verified.get("reason", "strict_verify_failed") or "strict_verify_failed"),
        }

        if verified.get("provisional_frame") is not None:
            try:
                provisional_local_frame = int(verified.get("provisional_frame") or 0)
                provisional_local_sec = float(
                    verified.get("provisional_sec", provisional_local_frame / max(source_fps, 1e-6)) or 0.0
                )
                provisional_global_sec = self._snap_to_frame(max(0.0, clip_global_offset + provisional_local_sec))
                provisional_global_frame = max(0, int(round(provisional_global_sec * fps)))
                result.update(
                    {
                        "provisional_frame": provisional_global_frame,
                        "provisional_sec": provisional_global_sec,
                        "provisional_mode": str(verified.get("provisional_mode", "") or ""),
                        "provisional_score": float(verified.get("provisional_score", 0.0) or 0.0),
                        "provisional_regions": int(verified.get("provisional_regions", 0) or 0),
                    }
                )
            except Exception:
                pass

        print(
            f"⚠️ [scan-cut] STRICT VERIFY REJECT reason={reason or '-'} "
            f"coarse_frame={coarse_frame} coarse={coarse_sec:.3f}s "
            f"detail={result['reason']}",
            flush=True,
        )
        return result

    def _scan_capture_image(self) -> bytes | None:
        """기존 호출부 호환용. 현재 위치 프레임을 OpenCV로 직접 읽는다."""
        try:
            sec = self._manual_global_sec_from_player()
        except Exception:
            try:
                sec = float(getattr(getattr(self, "timeline", None).canvas, "playhead_sec", 0.0) or 0.0)
            except Exception:
                sec = 0.0
        return self._scan_capture_image_at_global(sec)



    def _scan_image_delta(self, prev_image, next_image) -> float:
        deltas = self._scan_region_deltas(prev_image, next_image)
        if not deltas:
            self._scan_last_region_deltas = []
            self._scan_last_region_hits = 0
            return 0.0

        region_threshold = self._scan_region_threshold()
        hits = sum(1 for d in deltas if d >= region_threshold)
        self._scan_last_region_deltas = list(deltas)
        self._scan_last_region_hits = int(hits)

        ranked = sorted(deltas, reverse=True)
        top_n = ranked[: min(3, len(ranked))]
        return sum(top_n) / float(len(top_n) or 1)

    def _scan_get_cv2_module(self):
        """scan-cut 전용 OpenCV lazy import."""
        cv2_mod = getattr(self, "_scan_cv2_mod", None)
        if cv2_mod and cv2_mod is not False:
            return cv2_mod
        if cv2_mod is False:
            return None
        try:
            cv2_mod = __import__("cv2")
            self._scan_cv2_mod = cv2_mod
            return cv2_mod
        except Exception as exc:
            self._scan_cv2_mod = False
            print(f"⚠️ [scan-cut] OpenCV 사용 불가: {exc}", flush=True)
            return None

    def _scan_get_context_for_global_sec(self, global_sec: float) -> dict:
        """global sec 기준 멀티클립 context 확인."""
        if hasattr(self, "_resolve_active_context"):
            try:
                ctx = self._resolve_active_context(global_sec=float(global_sec))
                if isinstance(ctx, dict):
                    return ctx
            except Exception:
                pass
        return {"global_sec": float(global_sec), "local_sec": float(global_sec)}

    def _scan_source_and_local_sec(self, global_sec: float):
        """global sec에서 source path / local sec 추출."""
        ctx = self._scan_get_context_for_global_sec(global_sec)
        source = str(ctx.get("clip_file", "") or ctx.get("source_path", "") or "")
        if not source:
            vp = getattr(self, "video_player", None)
            source = str(getattr(vp, "_current_source_path", "") or "")

        try:
            local_sec = float(ctx.get("local_sec", global_sec) or global_sec)
        except Exception:
            local_sec = float(global_sec)

        return source, max(0.0, local_sec), ctx

    def _scan_get_cv2_capture(self, source_path: str):
        """같은 영상 파일은 VideoCapture를 계속 재사용한다."""
        if not source_path or not os.path.exists(source_path):
            return None

        cv2_mod = self._scan_get_cv2_module()
        if not cv2_mod:
            return None

        try:
            norm_path = os.path.normpath(str(source_path))
        except Exception:
            norm_path = str(source_path)

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
                print(f"⚠️ [scan-cut] VideoCapture open 실패: {norm_path}", flush=True)
                return None
            self._scan_cv2_capture = cap
            self._scan_cv2_source_path = norm_path
            self._scan_cv2_last_frame_idx = None
            return cap
        except Exception as exc:
            print(f"⚠️ [scan-cut] VideoCapture 예외: {exc}", flush=True)
            return None


    def _scan_image_backend_label(self) -> str:
        return "opencv-gray-cross"

    def _scan_frames_per_tick(self) -> int:
        settings = getattr(self, "settings", {}) or {}
        raw = os.environ.get("AI_SUBTITLE_SCAN_CUT_FRAMES_PER_TICK", settings.get("scan_cut_frames_per_tick", 16))
        try:
            return max(1, min(120, int(raw)))
        except Exception:
            return 16

    def _scan_preview_every_frames(self) -> int:
        settings = getattr(self, "settings", {}) or {}
        raw = os.environ.get("AI_SUBTITLE_SCAN_CUT_PREVIEW_EVERY_FRAMES", settings.get("scan_cut_preview_every_frames", 12))
        try:
            return max(1, min(240, int(raw)))
        except Exception:
            return 12

    def _scan_region_threshold(self) -> float:
        settings = getattr(self, "settings", {}) or {}
        raw = os.environ.get("AI_SUBTITLE_SCAN_CUT_REGION_THRESHOLD", settings.get("scan_cut_region_threshold", 18.0))
        try:
            return max(1.0, float(raw))
        except Exception:
            return 18.0

    def _scan_cross_regions_required(self) -> int:
        settings = getattr(self, "settings", {}) or {}
        raw = os.environ.get("AI_SUBTITLE_SCAN_CUT_CROSS_REGIONS_REQUIRED", settings.get("scan_cut_cross_regions_required", 3))
        try:
            return max(1, min(5, int(raw)))
        except Exception:
            return 3

    def _scan_cut_is_running(self) -> bool:
        return bool(getattr(self, "_scan_cut_state", None) or getattr(self, "_auto_cut_boundary_scan_active", False))

    def _scan_should_block_user_timeline_input(self) -> bool:
        return self._scan_cut_is_running()

    def _scan_set_timeline_input_locked(self, locked: bool) -> None:
        try:
            timeline = getattr(self, "timeline", None)
            canvas = getattr(timeline, "canvas", None)
            if canvas is not None:
                canvas._scan_cut_input_locked = bool(locked)
                canvas.setProperty("scan_cut_input_locked", bool(locked))
        except Exception:
            pass

    def _set_auto_cut_boundary_scan_active(self, active: bool) -> None:
        self._auto_cut_boundary_scan_active = bool(active)
        self._scan_set_timeline_input_locked(bool(active))
        try:
            if hasattr(self, "timeline") and hasattr(self.timeline, "set_playback_center_lock"):
                self.timeline.set_playback_center_lock(False)
            if hasattr(self, "timeline") and hasattr(self.timeline, "set_playhead_busy"):
                self.timeline.set_playhead_busy(self._scan_cut_is_running())
        except Exception:
            pass
        if not active:
            try:
                vp = getattr(self, "video_player", None)
                if vp is not None and hasattr(vp, "info_label"):
                    vp.info_label.setText("")
            except Exception:
                pass

    def _scan_cut_should_ignore_stale_preview_rows(self, rows: list[dict]) -> bool:
        if not rows or bool(getattr(self, "_auto_cut_boundary_scan_active", False)):
            return False
        if any(str(row.get("reason", "") or "") == "manual_roughcut_middle_right_click" for row in rows if isinstance(row, dict)):
            return False
        try:
            main_w = self.window()
        except Exception:
            return False
        for backend in (
            getattr(main_w, "backend", None),
            getattr(main_w, "backend_fast", None),
        ):
            if backend is None:
                continue
            try:
                prescan = getattr(backend, "_cut_boundary_prescan_thread", None)
                follower = getattr(backend, "_cut_boundary_follower_thread", None)
                scan_busy = bool(
                    (prescan is not None and prescan.is_alive())
                    or (follower is not None and follower.is_alive())
                )
                scan_completed = bool(getattr(backend, "_cut_boundary_prescan_completed", False))
            except Exception:
                continue
            if scan_completed and not scan_busy:
                return True
        return False

    def _set_auto_cut_boundary_scan_lines(self, times) -> None:
        if not times:
            self._auto_cut_boundary_scan_lines = []
            timeline = getattr(self, "timeline", None)
            if timeline is not None and hasattr(timeline, "set_scan_boundary_times"):
                timeline.set_scan_boundary_times([])
            return

        def _visible_preview_row(row) -> bool:
            if not isinstance(row, dict):
                return False
            if str(row.get("reason", "") or "") == "manual_roughcut_middle_right_click":
                return True
            if bool(
                row.get("scan_checked")
                or row.get("rollback_relocated")
                or row.get("follower_relocated")
                or row.get("middle_merge_preferred")
                or row.get("same_scene_color_similarity")
            ):
                return False
            status = str(row.get("status", "") or "").strip().lower()
            if status in {"checked", "verified", "confirmed", "accepted", "done"}:
                return False
            return True

        def _normalise_row(item):
            if isinstance(item, dict):
                row = dict(item)
                try:
                    sec = self._snap_to_frame(float(row.get("timeline_sec", row.get("time", row.get("start", 0.0))) or 0.0))
                except Exception:
                    return None
                if sec <= 0.0:
                    return None
                row["timeline_sec"] = sec
                row["time"] = sec
                row["status"] = str(row.get("status", "") or "provisional").lower()
                return row
            try:
                sec = self._snap_to_frame(float(item or 0.0))
            except Exception:
                return None
            if sec <= 0.0:
                return None
            return {"timeline_sec": sec, "time": sec, "status": "provisional"}

        cleaned = []
        for item in list(times or []):
            row = _normalise_row(item)
            if row is not None:
                cleaned.append(row)
        if self._scan_cut_should_ignore_stale_preview_rows(cleaned):
            return
        try:
            merged = []

            def _is_verified_row(row) -> bool:
                status = str(row.get("status", "") or "").lower()
                return status in {"verified", "confirmed"} or bool(row.get("verified"))

            def _status_rank(row):
                return 2 if _is_verified_row(row) else 1

            def _upsert(row):
                sec = float(row.get("timeline_sec", row.get("time", 0.0)) or 0.0)
                if sec <= 0.0:
                    return
                match_idx = None
                for idx, old in enumerate(merged):
                    old_sec = float(old.get("timeline_sec", old.get("time", 0.0)) or 0.0)
                    if abs(old_sec - sec) <= 0.055:
                        match_idx = idx
                        break
                if match_idx is None:
                    merged.append(row)
                    return
                old = merged[match_idx]
                if _status_rank(row) >= _status_rank(old):
                    # Once a candidate is verified, later provisional scan updates must not
                    # turn the visual marker back into the teal "unchecked" state.
                    if _status_rank(old) > _status_rank(row):
                        return
                    merged[match_idx] = {**old, **row}

            for item in list(getattr(self, "_auto_cut_boundary_scan_lines", []) or []):
                row = _normalise_row(item)
                if row is not None:
                    _upsert(row)
            for row in cleaned:
                _upsert(row)

            dedup = {}
            for row in merged:
                key = round(float(row.get("timeline_sec", row.get("time", 0.0)) or 0.0), 3)
                old = dedup.get(key)
                if old is None:
                    dedup[key] = row
                    continue
                if _status_rank(row) >= _status_rank(old):
                    dedup[key] = row
            cleaned = [
                dedup[key]
                for key in sorted(dedup.keys())
                if key > 0.0 and _visible_preview_row(dedup[key])
            ]
        except Exception:
            cleaned = [row for row in list(cleaned) if _visible_preview_row(row)]
        self._auto_cut_boundary_scan_lines = list(cleaned)
        timeline = getattr(self, "timeline", None)
        if timeline is None or not hasattr(timeline, "set_scan_boundary_times"):
            return
        changed = timeline.set_scan_boundary_times(list(cleaned))
        if changed is False:
            return
        if changed is True:
            return
        try:
            if hasattr(timeline, "canvas"):
                timeline.canvas.update()
            timeline.update()
        except Exception:
            pass

    def _on_provisional_cut_boundary_requested(self, global_sec: float) -> None:
        try:
            sec = self._snap_to_frame(float(global_sec or 0.0))
        except Exception:
            sec = float(global_sec or 0.0)
        if sec <= 0.0:
            return
        try:
            fps = float(self._current_frame_fps())
        except Exception:
            fps = 30.0
        try:
            frame = int(round(sec * fps))
        except Exception:
            frame = 0
        row = {
            "timeline_sec": sec,
            "time": sec,
            "start": sec,
            "timeline_frame": frame,
            "frame": frame,
            "fps": fps,
            "status": "provisional",
            "reason": "manual_roughcut_middle_right_click",
        }
        existing = list(getattr(self, "_auto_cut_boundary_scan_lines", []) or [])
        self._set_auto_cut_boundary_scan_lines([*existing, row])
        try:
            if hasattr(self, "_mark_dirty"):
                self._mark_dirty()
        except Exception:
            pass
        try:
            vp = getattr(self, "video_player", None)
            if vp is not None and hasattr(vp, "info_label"):
                vp.info_label.setText(f"임시 컷 경계 추가 · {sec:.3f}s")
        except Exception:
            pass

    def _on_provisional_cut_boundary_delete_requested(self, index: int, global_sec: float) -> None:
        try:
            sec = self._snap_to_frame(float(global_sec or 0.0))
        except Exception:
            sec = float(global_sec or 0.0)
        existing = list(getattr(self, "_auto_cut_boundary_scan_lines", []) or [])
        removed = False
        kept = []
        for row in existing:
            try:
                row_sec = float(row.get("timeline_sec", row.get("time", row.get("start", 0.0))) or 0.0) if isinstance(row, dict) else float(row or 0.0)
            except Exception:
                kept.append(row)
                continue
            if abs(row_sec - sec) <= 0.055:
                removed = True
                continue
            kept.append(row)

        try:
            idx = int(index)
        except Exception:
            idx = -1
        if not removed and 0 <= idx < len(existing):
            kept = list(existing)
            kept.pop(idx)
            removed = True
        if not removed:
            return
        self._auto_cut_boundary_scan_lines = []
        self._set_auto_cut_boundary_scan_lines(kept)
        try:
            canvas = getattr(getattr(self, "timeline", None), "canvas", None)
            if canvas is not None:
                canvas._hover_scan_boundary_idx = None
                canvas.update()
        except Exception:
            pass
        try:
            if hasattr(self, "_mark_dirty"):
                self._mark_dirty()
        except Exception:
            pass
        try:
            vp = getattr(self, "video_player", None)
            if vp is not None and hasattr(vp, "info_label"):
                vp.info_label.setText(f"임시 컷 경계 삭제 · {sec:.3f}s")
        except Exception:
            pass

    def _preview_auto_cut_boundary_scan(self, current_sec: float, next_sec: float = 0.0) -> None:
        self._set_auto_cut_boundary_scan_active(True)
        self._scan_preview_global_sec(float(current_sec or 0.0), show_thumbnail=False)
        try:
            vp = getattr(self, "video_player", None)
            if vp is not None and hasattr(vp, "info_label"):
                vp.info_label.setText(f"컷 경계 탐색 중 · {float(current_sec or 0.0):.3f}s")
        except Exception:
            pass


    def _scan_fast_thumbnail_enabled(self) -> bool:
        """
        scan-cut 진행 중 비디오 플레이어 seek 대신 OpenCV 썸네일을 빠르게 표시할지 여부.
        """
        settings = getattr(self, "settings", {}) or {}
        raw = settings.get("scan_cut_preview_thumbnail_enabled", True)
        try:
            if isinstance(raw, str):
                return raw.strip().lower() not in ("0", "false", "no", "off")
            return bool(raw)
        except Exception:
            return True

    def _scan_preview_thumbnail_size(self) -> tuple[int, int]:
        """
        scan-cut preview thumbnail 최대 크기.
        너무 크게 뽑으면 느려지므로 기본 640x360.
        """
        settings = getattr(self, "settings", {}) or {}
        try:
            w = int(settings.get("scan_cut_preview_thumbnail_width", 640))
            h = int(settings.get("scan_cut_preview_thumbnail_height", 360))
        except Exception:
            w, h = 640, 360
        return max(160, min(w, 1280)), max(90, min(h, 720))

    def _scan_extract_preview_pixmap_at_global(self, global_sec: float):
        """
        OpenCV로 global_sec 위치의 프레임을 빠르게 읽어 QPixmap으로 변환한다.

        목적:
        - 컷 탐색 중 QMediaPlayer seek 비용을 줄인다.
        - 탐색 위치를 비디오 화면에 썸네일처럼 빠르게 표시한다.
        """
        try:
            from PyQt6.QtGui import QImage, QPixmap
        except Exception:
            return None

        cv2_mod = self._scan_get_cv2_module() if hasattr(self, "_scan_get_cv2_module") else None
        if not cv2_mod:
            return None

        try:
            source_path, local_sec, _ctx = self._scan_source_and_local_sec(float(global_sec))
        except Exception:
            return None

        if not source_path:
            return None

        cap = self._scan_get_cv2_capture(source_path) if hasattr(self, "_scan_get_cv2_capture") else None
        if cap is None:
            return None

        try:
            fps = float(cap.get(cv2_mod.CAP_PROP_FPS) or 0.0)
        except Exception:
            fps = 0.0

        if fps <= 1.0:
            fps = self._current_frame_fps()

        frame_idx = max(0, int(round(float(local_sec) * fps)))

        try:
            current_pos = int(cap.get(cv2_mod.CAP_PROP_POS_FRAMES) or 0)
            if current_pos != frame_idx:
                cap.set(cv2_mod.CAP_PROP_POS_FRAMES, frame_idx)

            ok, frame = cap.read()
            if not ok or frame is None:
                return None

            max_w, max_h = self._scan_preview_thumbnail_size()
            h, w = frame.shape[:2]
            if w <= 0 or h <= 0:
                return None

            scale = min(max_w / float(w), max_h / float(h), 1.0)
            if scale < 1.0:
                nw = max(1, int(w * scale))
                nh = max(1, int(h * scale))
                frame = cv2_mod.resize(frame, (nw, nh), interpolation=cv2_mod.INTER_AREA)

            rgb = cv2_mod.cvtColor(frame, cv2_mod.COLOR_BGR2RGB)
            hh, ww = rgb.shape[:2]
            bytes_per_line = int(rgb.strides[0])
            qimg = QImage(rgb.data, ww, hh, bytes_per_line, QImage.Format.Format_RGB888).copy()
            return QPixmap.fromImage(qimg)
        except Exception:
            return None

    def _scan_show_fast_thumbnail_at_global(self, global_sec: float) -> bool:
        """
        scan-cut 진행 중 OpenCV 썸네일을 비디오 화면에 즉시 표시한다.
        성공하면 True.
        """
        if not self._scan_fast_thumbnail_enabled():
            return False

        pixmap = self._scan_extract_preview_pixmap_at_global(global_sec)
        if pixmap is None or pixmap.isNull():
            return False

        vp = getattr(self, "video_player", None)
        if vp is None:
            return False

        try:
            if hasattr(vp, "thumb_label"):
                vp.thumb_label.set_pixmap(pixmap)
            if hasattr(vp, "video_stack") and hasattr(vp, "thumb_label"):
                vp.video_stack.setCurrentWidget(vp.thumb_label)

            try:
                _source_path, local_sec, ctx = self._scan_source_and_local_sec(float(global_sec))
            except Exception:
                local_sec, ctx = float(global_sec), {}
            try:
                vp.current_time = float(local_sec)
                clip_total = float((ctx or {}).get("duration", 0.0) or 0.0)
                if clip_total > 0.0:
                    vp.total_time = clip_total
                if hasattr(vp, "_last_time_label_ms"):
                    vp._last_time_label_ms = -250
                if hasattr(vp, "_ui_tick"):
                    vp._ui_tick()
            except Exception:
                pass

            try:
                if hasattr(vp, "set_subtitle_display_time"):
                    # global/local 차이가 있어도 preview 표시용이므로 실패해도 무시
                    vp.set_subtitle_display_time(float(global_sec), refresh=True)
            except Exception:
                pass

            try:
                if hasattr(vp, "info_label"):
                    vp.info_label.setText(f"컷 경계 탐색 중 · {float(global_sec):.3f}s")
            except Exception:
                pass

            return True
        except Exception:
            return False


    def _scan_preview_global_sec(self, global_sec: float, *, show_thumbnail: bool = True) -> None:
        """
        scan-cut 진행 중 preview.

        변경점:
        - 플레이헤드는 계속 움직인다.
        - 비디오 화면은 QMediaPlayer seek보다 빠른 OpenCV 썸네일 표시를 우선한다.
        - 썸네일 표시 실패 시에만 기존 비디오 seek 방식으로 fallback한다.
        """
        try:
            global_sec = self._snap_to_frame(float(global_sec))
        except Exception:
            return

        # 1) 플레이헤드 이동
        try:
            self._reset_playhead_smoothing(global_sec)
        except Exception:
            pass

        try:
            if hasattr(self, "timeline"):
                self.timeline.set_playback_center_lock(False)
                self.timeline.set_playhead(global_sec)
        except Exception:
            pass

        if not show_thumbnail:
            return

        # 2) 캐시 썸네일 우선: 같은 시점을 반복 방문해도 ffmpeg/OpenCV 비용이 덜 든다.
        try:
            source_path, local_sec, _ctx = self._scan_source_and_local_sec(global_sec)
            vp = getattr(self, "video_player", None)
            if vp is not None and source_path and hasattr(vp, "show_cached_thumbnail_at"):
                if vp.show_cached_thumbnail_at(source_path, local_sec, width=self._scan_preview_thumbnail_size()[0]):
                    if hasattr(vp, "info_label"):
                        vp.info_label.setText(f"컷 경계 탐색 중 · {float(global_sec):.3f}s")
                    try:
                        if hasattr(vp, "_last_time_label_ms"):
                            vp._last_time_label_ms = -250
                        vp.current_time = float(local_sec)
                        clip_total = float((_ctx or {}).get("duration", 0.0) or 0.0)
                        if clip_total > 0.0:
                            vp.total_time = clip_total
                        vp._ui_tick()
                    except Exception:
                        pass
                    return
        except Exception:
            pass

        # 3) 제일 빠른 실시간 경로: OpenCV 썸네일을 video 화면에 표시
        try:
            if self._scan_show_fast_thumbnail_at_global(global_sec):
                return
        except Exception:
            pass

        # 4) fallback: 기존 비디오 플레이어 seek
        try:
            if hasattr(self, "_resolve_active_context"):
                ctx = self._resolve_active_context(global_sec=global_sec)
                if hasattr(self, "timeline") and hasattr(self.timeline, "canvas"):
                    try:
                        self.timeline.canvas._active_clip_idx = int(ctx.get("clip_idx", 0) or 0)
                    except Exception:
                        pass
                local_sec = float(ctx.get("local_sec", global_sec) or 0.0)
                if hasattr(self, "video_player"):
                    if hasattr(self.video_player, "pause_video"):
                        self.video_player.pause_video()
                    if hasattr(self.video_player, "frame_step_seek"):
                        self.video_player.frame_step_seek(local_sec)
                    elif hasattr(self.video_player, "seek_direct"):
                        self.video_player.seek_direct(local_sec)
            elif hasattr(self, "video_player"):
                if hasattr(self.video_player, "pause_video"):
                    self.video_player.pause_video()
                if hasattr(self.video_player, "frame_step_seek"):
                    self.video_player.frame_step_seek(global_sec)
                elif hasattr(self.video_player, "seek_direct"):
                    self.video_player.seek_direct(global_sec)
        except Exception:
            pass

        try:
            if hasattr(self, "_sync_after_manual_seek"):
                self._sync_after_manual_seek(global_sec)
        except Exception:
            pass

    def _scan_make_cross_region_thumbnails(self, frame, cv2_mod, scale_w: int, scale_h: int):
        try:
            h, w = frame.shape[:2]
        except Exception:
            return None
        if w <= 0 or h <= 0:
            return None

        xs = [0, int(w / 3), int(w * 2 / 3), w]
        ys = [0, int(h / 3), int(h * 2 / 3), h]

        cells = [
            (1, 0),  # top center
            (0, 1),  # mid left
            (1, 1),  # center
            (2, 1),  # mid right
            (1, 2),  # bottom center
        ]

        result = []
        for cx, cy in cells:
            roi = frame[ys[cy]:ys[cy + 1], xs[cx]:xs[cx + 1]]
            if roi is None or roi.size == 0:
                return None
            gray = cv2_mod.cvtColor(roi, cv2_mod.COLOR_BGR2GRAY)
            small = cv2_mod.resize(gray, (int(scale_w), int(scale_h)), interpolation=cv2_mod.INTER_AREA)
            result.append(small.tobytes())
        return tuple(result)

    def _scan_delta_bytes(self, a: bytes, b: bytes) -> float:
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

    def _scan_region_deltas(self, prev_image, next_image):
        if not prev_image or not next_image:
            return []
        if isinstance(prev_image, (tuple, list)) and isinstance(next_image, (tuple, list)):
            n = min(len(prev_image), len(next_image))
            return [self._scan_delta_bytes(prev_image[i], next_image[i]) for i in range(n)]
        return [self._scan_delta_bytes(prev_image, next_image)]



    def _scan_capture_image_at_global(self, global_sec: float):
        cv2_mod = self._scan_get_cv2_module()
        if not cv2_mod:
            return None

        source_path, local_sec, _ctx = self._scan_source_and_local_sec(global_sec)
        if not source_path:
            return None

        cap = self._scan_get_cv2_capture(source_path)
        if cap is None:
            return None

        settings = getattr(self, "settings", {}) or {}
        try:
            scale_w = int(settings.get("scan_cut_sample_width", 18))
            scale_h = int(settings.get("scan_cut_sample_height", 10))
        except Exception:
            scale_w, scale_h = 18, 10

        scale_w = max(8, min(scale_w, 48))
        scale_h = max(6, min(scale_h, 27))

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

            if not bool(getattr(self, "_scan_logged_capture_resolution", False)):
                self._scan_logged_capture_resolution = True
                print(
                    f"🔎 [scan-cut] source_resolution={w}x{h} "
                    f"sample_region=3x3-cross sample_each={scale_w}x{scale_h} mode=cross9",
                    flush=True,
                )

            return self._scan_make_cross_region_thumbnails(frame, cv2_mod, scale_w, scale_h)
        except Exception:
            return None


    def _scan_hard_threshold(self) -> float:
        """
        즉시 컷으로 판단할 hard threshold.
        이 값 이상이면 연속 hit 없이 바로 컷으로 본다.
        """
        settings = getattr(self, "settings", {}) or {}
        raw = os.environ.get("AI_SUBTITLE_SCAN_CUT_HARD_THRESHOLD", settings.get("scan_cut_hard_threshold", 45.0))
        try:
            return max(1.0, float(raw))
        except Exception:
            return 45.0


    def _scan_consecutive_hits_required(self) -> int:
        """
        작은 움직임 한 번으로 멈추지 않게 하기 위한 연속 hit 필요 개수.
        """
        settings = getattr(self, "settings", {}) or {}
        raw = os.environ.get("AI_SUBTITLE_SCAN_CUT_CONSECUTIVE_HITS", settings.get("scan_cut_consecutive_hits", 2))
        try:
            return max(1, int(raw))
        except Exception:
            return 2


    def _scan_threshold(self) -> float:
        """
        scan-cut 픽셀 변화량 threshold.

        기존 8.0은 너무 낮아서 조명 변화/움직임에도 멈출 수 있다.
        기본값을 24.0으로 올려서 확실한 컷에서만 멈추게 한다.
        환경변수 AI_SUBTITLE_SCAN_CUT_THRESHOLD 또는 settings["scan_cut_threshold"]로 조정 가능.
        """
        settings = getattr(self, "settings", {}) or {}
        raw = os.environ.get("AI_SUBTITLE_SCAN_CUT_THRESHOLD", settings.get("scan_cut_threshold", 24.0))
        try:
            return max(1.0, float(raw))
        except Exception:
            return 24.0

    def _scan_interval_ms(self) -> int:
        settings = getattr(self, "settings", {}) or {}
        raw = os.environ.get("AI_SUBTITLE_SCAN_CUT_INTERVAL_MS", settings.get("scan_cut_interval_ms", 1))
        try:
            return max(1, int(raw))
        except Exception:
            return 1


    def _scan_max_frames(self) -> int:
        """
        scan-cut 최대 탐색 프레임 수.

        0이면 제한 없음.
        기존 기본값 1800은 60fps에서 약 30초라 긴 컷 탐색에 너무 짧다.
        """
        settings = getattr(self, "settings", {}) or {}
        raw = os.environ.get("AI_SUBTITLE_SCAN_CUT_MAX_FRAMES", settings.get("scan_cut_max_frames", 0))
        try:
            return max(0, int(raw))
        except Exception:
            return 0

    def _set_scan_cut_button_active(self, direction: int):
        try:
            video_player = getattr(self, "video_player", None)
            if video_player is not None and hasattr(video_player, "set_scan_cut_active"):
                video_player.set_scan_cut_active(direction)
        except Exception:
            pass
        try:
            timeline = getattr(self, "timeline", None)
            if timeline is not None and hasattr(timeline, "set_playhead_busy"):
                timeline.set_playhead_busy(bool(direction) or bool(getattr(self, "_auto_cut_boundary_scan_active", False)))
        except Exception:
            pass

    def _cancel_scan_cut(self, reason: str = "cancelled", *, update_label: bool = True):
        try:
            if hasattr(self, "_scan_cut_timer"):
                self._scan_cut_timer.stop()
        except Exception:
            pass

        self._scan_cut_pending_direction = 0
        self._scan_cut_launch_token = None
        self._scan_cut_state = None
        self._set_scan_cut_button_active(0)

        if update_label:
            try:
                self.video_player.info_label.setText("컷 경계 탐색 취소")
            except Exception:
                pass

        print(f"🟢 [scan-cut] CANCEL reason={reason}", flush=True)

    def _scan_live_visual_jump_enabled(self) -> bool:
        settings = getattr(self, "settings", {}) or {}
        raw = settings.get("scan_cut_live_visual_enabled", True)
        if isinstance(raw, str):
            return raw.strip().lower() not in {"0", "false", "no", "off", "disabled", "미사용"}
        return bool(raw)

    def _scan_live_visual_follower_verify_enabled(self) -> bool:
        settings = getattr(self, "settings", {}) or {}
        raw = settings.get("scan_cut_live_visual_follower_verify_enabled", True)
        if isinstance(raw, str):
            return raw.strip().lower() not in {"0", "false", "no", "off", "disabled", "미사용"}
        return bool(raw)

    def _scan_verify_live_visual_candidate(self, candidate: dict | None, *, direction: int) -> dict | None:
        if not isinstance(candidate, dict):
            return candidate
        if not self._scan_live_visual_follower_verify_enabled():
            return candidate

        try:
            fps = float(self._current_frame_fps())
        except Exception:
            fps = 30.0

        try:
            pioneer_frame = int(candidate.get("boundary_frame", 0) or 0)
        except Exception:
            pioneer_frame = 0
        if pioneer_frame < 0:
            return candidate

        verified = self._scan_verify_cut_boundary_candidate(
            pioneer_frame,
            fps,
            reason=f"live_visual_follower dir={int(1 if int(direction) > 0 else -1)}",
        )
        if not isinstance(verified, dict) or not bool(verified.get("available")):
            return candidate
        if not bool(verified.get("passed")):
            try:
                provisional_frame = int(verified.get("provisional_frame", -1) or -1)
            except Exception:
                provisional_frame = -1
            provisional_window = max(2, min(24, int(round(max(fps, 1.0) * 0.25))))
            if provisional_frame >= 0 and abs(provisional_frame - pioneer_frame) <= provisional_window:
                provisional_sec = self._snap_to_frame(
                    float(verified.get("provisional_sec", provisional_frame / max(fps, 1e-6)) or (provisional_frame / max(fps, 1e-6)))
                )
                merged = dict(candidate)
                merged.update(
                    {
                        "boundary_frame": int(provisional_frame),
                        "boundary_sec": float(provisional_sec),
                        "follower_verified": True,
                        "follower_verified_provisional": True,
                        "follower_verified_frame": int(provisional_frame),
                        "follower_verified_sec": float(provisional_sec),
                        "follower_verified_score": float(verified.get("provisional_score", 0.0) or 0.0),
                        "follower_verified_regions": int(verified.get("provisional_regions", 0) or 0),
                        "follower_verified_mode": str(verified.get("provisional_mode", verified.get("reason", "strict_provisional")) or "strict_provisional"),
                        "follower_verified_reason": str(verified.get("reason", "strict_provisional") or "strict_provisional"),
                    }
                )
                print(
                    f"🧭 [scan-cut-live] follower provisional pioneer={pioneer_frame} -> frame={provisional_frame} "
                    f"mode={merged['follower_verified_mode']} score={merged['follower_verified_score']:.2f} "
                    f"regions={merged['follower_verified_regions']}",
                    flush=True,
                )
                return merged
            print(
                f"↩️ [scan-cut-live] follower verify miss pioneer={pioneer_frame} "
                f"reason={verified.get('reason', '-')}",
                flush=True,
            )
            return candidate

        try:
            verified_sec = self._snap_to_frame(float(verified.get("sec", 0.0) or 0.0))
        except Exception:
            verified_sec = float(candidate.get("boundary_sec", 0.0) or 0.0)
        verified_frame = max(0, int(round(verified_sec * max(fps, 1e-6))))

        merged = dict(candidate)
        merged.update(
            {
                "boundary_frame": int(verified_frame),
                "boundary_sec": float(verified_sec),
                "follower_verified": True,
                "follower_verified_frame": int(verified_frame),
                "follower_verified_sec": float(verified_sec),
                "follower_verified_score": float(verified.get("score", 0.0) or 0.0),
                "follower_verified_regions": int(verified.get("regions", 0) or 0),
                "follower_verified_mode": str(verified.get("mode", verified.get("reason", "strict_verify")) or "strict_verify"),
                "follower_verified_reason": str(verified.get("reason", verified.get("mode", "strict_verify")) or "strict_verify"),
            }
        )
        print(
            f"🧭 [scan-cut-live] follower verify pioneer={pioneer_frame} -> frame={verified_frame} "
            f"mode={merged['follower_verified_mode']} score={merged['follower_verified_score']:.2f} "
            f"regions={merged['follower_verified_regions']}",
            flush=True,
        )
        return merged

    def _scan_live_visual_search_frames(self, fps: float) -> int:
        settings = getattr(self, "settings", {}) or {}
        try:
            explicit = int(settings.get("scan_cut_live_visual_max_frames", 0) or 0)
        except Exception:
            explicit = 0
        if explicit > 0:
            return max(12, min(explicit, 1800))
        try:
            sec = float(settings.get("scan_cut_live_visual_max_sec", 8.0) or 8.0)
        except Exception:
            sec = 8.0
        return max(12, min(int(round(max(0.5, sec) * max(float(fps or 30.0), 1.0))), 1800))

    def _scan_live_visual_coarse_search_frames(self, fps: float) -> int:
        settings = getattr(self, "settings", {}) or {}
        try:
            explicit = int(settings.get("scan_cut_live_visual_coarse_max_frames", 0) or 0)
        except Exception:
            explicit = 0
        if explicit > 0:
            return max(60, min(explicit, 3600))
        try:
            sec = float(settings.get("scan_cut_live_visual_coarse_max_sec", 8.0) or 8.0)
        except Exception:
            sec = 8.0
        return max(60, min(int(round(max(1.0, sec) * max(float(fps or 30.0), 1.0))), 3600))

    def _scan_live_visual_coarse_stride_frames(self, fps: float) -> int:
        settings = getattr(self, "settings", {}) or {}
        try:
            explicit = int(settings.get("scan_cut_live_visual_coarse_stride_frames", 0) or 0)
        except Exception:
            explicit = 0
        if explicit > 0:
            return max(3, min(explicit, 120))
        return max(10, min(int(round(max(float(fps or 30.0), 1.0) * 0.33)), 30))

    def _scan_live_visual_coarse_width(self) -> int:
        settings = getattr(self, "settings", {}) or {}
        base_width = self._scan_live_visual_width()
        try:
            return max(320, min(int(settings.get("scan_cut_live_visual_coarse_width", min(base_width, 640)) or min(base_width, 640)), 1920))
        except Exception:
            return min(base_width, 640)

    def _scan_live_visual_candidate_topk(self) -> int:
        settings = getattr(self, "settings", {}) or {}
        try:
            return max(2, min(int(settings.get("scan_cut_live_visual_candidate_topk", 6) or 6), 12))
        except Exception:
            return 6

    def _scan_live_visual_candidate_min_score(self) -> float:
        settings = getattr(self, "settings", {}) or {}
        try:
            return max(0.25, min(float(settings.get("scan_cut_live_visual_candidate_min_score", 0.90) or 0.90), 4.0))
        except Exception:
            return 0.90

    def _scan_live_native_coarse_enabled(self) -> bool:
        settings = getattr(self, "settings", {}) or {}
        value = settings.get("scan_cut_live_native_coarse_enabled")
        if value is None:
            value = settings.get("runtime_native_cut_boundary_enabled", True)
        try:
            text = str(value).strip().lower()
            return text not in {"0", "false", "off", "no", "disabled", "disable", "끔"}
        except Exception:
            return bool(value)

    def _scan_live_visual_interval_margin_frames(self, fps: float, stride_frames: int) -> int:
        settings = getattr(self, "settings", {}) or {}
        try:
            explicit = int(settings.get("scan_cut_live_visual_interval_margin_frames", 0) or 0)
        except Exception:
            explicit = 0
        if explicit > 0:
            return max(2, min(explicit, 240))
        return max(int(stride_frames or 0), max(4, int(round(max(float(fps or 30.0), 1.0) * 0.25))))

    def _scan_live_visual_width(self) -> int:
        settings = getattr(self, "settings", {}) or {}
        try:
            return max(320, min(int(settings.get("scan_cut_live_visual_width", 960) or 960), 3840))
        except Exception:
            return 960

    def _scan_live_visual_refine_width(self) -> int:
        settings = getattr(self, "settings", {}) or {}
        try:
            return max(320, min(int(settings.get("scan_cut_live_visual_refine_width", 1920) or 1920), 4096))
        except Exception:
            return 1920

    def _scan_live_visual_refine_radius(self) -> int:
        settings = getattr(self, "settings", {}) or {}
        try:
            return max(1, min(int(settings.get("scan_cut_live_visual_refine_radius", 2) or 2), 6))
        except Exception:
            return 2

    def _scan_prepare_visual_frame_payload(self, global_frame: int, *, max_width: int, cache: dict | None = None):
        key = (int(global_frame), int(max_width))
        if isinstance(cache, dict) and key in cache:
            return cache.get(key)

        cv2_mod = self._scan_get_cv2_module()
        if not cv2_mod:
            return None

        try:
            from core.visual_cut_jump import prepare_visual_cut_frame
        except Exception as exc:
            print(f"⚠️ [scan-cut] visual jump helper import 실패: {exc}", flush=True)
            return None

        try:
            fps = float(self._current_frame_fps())
        except Exception:
            fps = 30.0
        global_sec = max(0.0, float(int(global_frame)) / max(fps, 1e-6))

        try:
            source_path, local_sec, ctx = self._scan_source_and_local_sec(global_sec)
        except Exception:
            return None
        if not source_path:
            return None

        cap = self._scan_get_cv2_capture(source_path)
        if cap is None:
            return None

        try:
            source_fps = float(cap.get(cv2_mod.CAP_PROP_FPS) or 0.0)
        except Exception:
            source_fps = 0.0
        if source_fps <= 1.0:
            source_fps = fps
        local_frame = max(0, int(round(float(local_sec) * source_fps)))

        try:
            current_pos = int(cap.get(cv2_mod.CAP_PROP_POS_FRAMES) or 0)
            if current_pos != local_frame:
                cap.set(cv2_mod.CAP_PROP_POS_FRAMES, local_frame)
            ok, frame_bgr = cap.read()
        except Exception:
            return None
        if not ok or frame_bgr is None:
            return None

        prepared = prepare_visual_cut_frame(frame_bgr, cv2_mod, max_width=int(max_width))
        if not isinstance(prepared, dict):
            return None

        payload = {
            **prepared,
            "global_frame": int(global_frame),
            "global_sec": float(global_sec),
            "source_path": str(source_path),
            "local_sec": float(local_sec),
            "local_frame": int(local_frame),
            "clip_idx": int((ctx or {}).get("clip_idx", 0) or 0),
        }
        if isinstance(cache, dict):
            cache[key] = payload
        return payload

    def _scan_refine_live_visual_cut(self, candidate: dict, *, coarse_history: list[dict] | None = None):
        if not isinstance(candidate, dict):
            return candidate

        refine_width = self._scan_live_visual_refine_width()
        coarse_width = int(candidate.get("analysis_width", 0) or 0)
        if refine_width <= 0 or (coarse_width > 0 and refine_width <= coarse_width):
            return candidate

        cv2_mod = self._scan_get_cv2_module()
        if not cv2_mod:
            return candidate

        try:
            from core.visual_cut_jump import (
                create_visual_cut_flow_engine,
                score_visual_cut_metrics,
                visual_cut_pair_metrics,
            )
        except Exception:
            return candidate

        try:
            frame = int(candidate.get("boundary_frame"))
        except Exception:
            return candidate

        radius = self._scan_live_visual_refine_radius()
        start_frame = max(0, frame - radius)
        end_frame = max(start_frame, frame + radius)
        cache: dict = {}
        settings = getattr(self, "settings", {}) or {}
        backend_preference = str(settings.get("scan_cut_dense_flow_backend", "dis") or "dis").strip().lower()
        flow_engine, _backend = create_visual_cut_flow_engine(cv2_mod, backend_preference=backend_preference)
        history = list(coarse_history or [])[-12:]
        best = dict(candidate)

        for left_frame in range(start_frame, end_frame + 1):
            left_payload = self._scan_prepare_visual_frame_payload(left_frame, max_width=refine_width, cache=cache)
            right_payload = self._scan_prepare_visual_frame_payload(left_frame + 1, max_width=refine_width, cache=cache)
            if not left_payload or not right_payload:
                continue
            metric = visual_cut_pair_metrics(
                left_payload,
                right_payload,
                cv2_mod,
                flow_engine=flow_engine,
                backend_preference=backend_preference,
            )
            if not isinstance(metric, dict):
                continue
            metric.update(
                {
                    "boundary_frame": int(left_frame),
                    "boundary_sec": float(left_payload["global_sec"]),
                    "left_frame": int(left_frame),
                    "right_frame": int(left_frame + 1),
                    "analysis_width": int(refine_width),
                    "source_changed": bool(left_payload.get("source_path") != right_payload.get("source_path")),
                }
            )
            scored = score_visual_cut_metrics(metric, history=history, settings=settings)
            history.append(metric)
            history = history[-12:]
            if not isinstance(scored, dict):
                continue
            if float(scored.get("score", 0.0) or 0.0) >= float(best.get("score", 0.0) or 0.0):
                best = dict(scored)

        if int(best.get("analysis_width", 0) or 0) == refine_width:
            best["refined"] = True
        return best

    def _scan_select_live_visual_candidates(
        self,
        candidates: list[dict],
        *,
        stride_frames: int,
        top_k: int,
    ) -> list[dict]:
        if not candidates:
            return []
        selected: list[dict] = []
        native_coarse = any(bool((row or {}).get("coarse_native")) for row in list(candidates or []))
        overlap_margin = 0 if native_coarse else max(2, int(round(max(int(stride_frames or 0), 1) * 0.5)))
        for item in sorted(
            [dict(row) for row in list(candidates or []) if isinstance(row, dict)],
            key=lambda row: (
                float(row.get("score", 0.0) or 0.0),
                float(row.get("edge_residual", 0.0) or 0.0),
                float(row.get("edge_diff", 0.0) or 0.0),
            ),
            reverse=True,
        ):
            start = int(item.get("interval_start_frame", item.get("boundary_frame", 0)) or 0)
            end = int(item.get("interval_end_frame", start) or start)
            overlaps = False
            for chosen in selected:
                chosen_start = int(chosen.get("interval_start_frame", chosen.get("boundary_frame", 0)) or 0)
                chosen_end = int(chosen.get("interval_end_frame", chosen_start) or chosen_start)
                if overlap_margin <= 0:
                    overlaps = max(start, chosen_start) < min(end, chosen_end)
                else:
                    overlaps = max(start, chosen_start) <= (min(end, chosen_end) + overlap_margin)
                if overlaps:
                    overlaps = True
                    break
            if overlaps:
                continue
            selected.append(item)
            if len(selected) >= max(1, int(top_k or 1)):
                break
        return selected

    def _scan_is_live_visual_coarse_peak(
        self,
        prev_item: dict | None,
        current_item: dict | None,
        next_item: dict | None,
        *,
        min_score: float,
    ) -> bool:
        if not isinstance(current_item, dict):
            return False

        current_score = float(current_item.get("score", 0.0) or 0.0)
        if current_score < float(min_score or 0.0):
            return False

        prev_score = float((prev_item or {}).get("score", 0.0) or 0.0)
        next_score = float((next_item or {}).get("score", 0.0) or 0.0)
        if current_score < prev_score or current_score < next_score:
            return False

        current_residual = float(current_item.get("edge_residual", 0.0) or 0.0)
        current_diff = float(current_item.get("edge_diff", 0.0) or 0.0)
        prev_residual = float((prev_item or {}).get("edge_residual", 0.0) or 0.0)
        next_residual = float((next_item or {}).get("edge_residual", 0.0) or 0.0)
        prev_diff = float((prev_item or {}).get("edge_diff", 0.0) or 0.0)
        next_diff = float((next_item or {}).get("edge_diff", 0.0) or 0.0)

        return (
            current_residual >= max(prev_residual, next_residual)
            or current_diff >= max(prev_diff, next_diff)
        )

    def _scan_find_live_visual_cut_in_window(
        self,
        start_frame: int,
        end_frame: int,
        *,
        analysis_width: int,
        direction: int,
        payload_cache: dict | None = None,
        coarse_history: list[dict] | None = None,
    ):
        cv2_mod = self._scan_get_cv2_module()
        if not cv2_mod:
            return None

        try:
            from core.visual_cut_jump import (
                create_visual_cut_flow_engine,
                is_visual_cut_peak,
                visual_cut_pair_metrics,
            )
        except Exception:
            return None

        left_bound = max(0, min(int(start_frame or 0), int(end_frame or 0)))
        right_bound = max(left_bound + 1, max(int(start_frame or 0), int(end_frame or 0)))
        if right_bound <= left_bound:
            return None

        settings = getattr(self, "settings", {}) or {}
        backend_preference = str(settings.get("scan_cut_dense_flow_backend", "dis") or "dis").strip().lower()
        flow_engine, _backend = create_visual_cut_flow_engine(cv2_mod, backend_preference=backend_preference)
        raw_history: list[dict] = []
        best = None

        for left_frame in range(left_bound, right_bound):
            left_payload = self._scan_prepare_visual_frame_payload(left_frame, max_width=analysis_width, cache=payload_cache)
            right_payload = self._scan_prepare_visual_frame_payload(left_frame + 1, max_width=analysis_width, cache=payload_cache)
            if not left_payload or not right_payload:
                continue
            metric = visual_cut_pair_metrics(
                left_payload,
                right_payload,
                cv2_mod,
                flow_engine=flow_engine,
                backend_preference=backend_preference,
            )
            if not isinstance(metric, dict):
                continue
            metric.update(
                {
                    "boundary_frame": int(left_frame),
                    "boundary_sec": float(left_payload["global_sec"]),
                    "left_frame": int(left_frame),
                    "right_frame": int(left_frame + 1),
                    "analysis_width": int(analysis_width),
                    "source_changed": bool(left_payload.get("source_path") != right_payload.get("source_path")),
                }
            )
            raw_history.append(metric)
            if len(raw_history) < 3:
                continue
            history = list(coarse_history or [])[-6:] + raw_history[max(0, len(raw_history) - 14):-2]
            scored = is_visual_cut_peak(
                raw_history[-3],
                raw_history[-2],
                raw_history[-1],
                history=history[-12:],
                settings=settings,
            )
            if not bool(scored.get("passed")):
                continue
            scored["direction"] = int(1 if int(direction) > 0 else -1)
            if best is None or float(scored.get("score", 0.0) or 0.0) > float(best.get("score", 0.0) or 0.0):
                best = dict(scored)
        return best

    def _scan_find_live_visual_cut(self, direction: int):
        if not self._scan_live_visual_jump_enabled():
            return None

        cv2_mod = self._scan_get_cv2_module()
        if not cv2_mod:
            return None

        try:
            from core.visual_cut_jump import (
                create_visual_cut_flow_engine,
                is_visual_cut_peak,
                native_visual_cut_coarse_series,
                score_visual_cut_coarse_metrics,
                visual_cut_pair_metrics,
            )
        except Exception as exc:
            print(f"⚠️ [scan-cut] visual jump helper 준비 실패: {exc}", flush=True)
            return None
        try:
            from core.visual_cut_jump import score_visual_cut_metrics
        except Exception as exc:
            print(f"⚠️ [scan-cut] visual jump scoring 준비 실패: {exc}", flush=True)
            return None

        try:
            fps = float(self._current_frame_fps())
        except Exception:
            fps = 30.0
        try:
            direction_i = 1 if int(direction) > 0 else -1
        except Exception:
            direction_i = 1
        try:
            start_sec = float(self._manual_global_sec_from_player())
        except Exception:
            start_sec = 0.0
        start_frame = max(0, int(round(start_sec * fps)))
        fine_width = self._scan_live_visual_width()
        coarse_width = self._scan_live_visual_coarse_width()
        coarse_stride = self._scan_live_visual_coarse_stride_frames(fps)
        coarse_max_frames = self._scan_live_visual_coarse_search_frames(fps)
        candidate_topk = self._scan_live_visual_candidate_topk()
        candidate_min_score = self._scan_live_visual_candidate_min_score()
        interval_margin = self._scan_live_visual_interval_margin_frames(fps, coarse_stride)
        settings = getattr(self, "settings", {}) or {}
        backend_preference = str(settings.get("scan_cut_dense_flow_backend", "dis") or "dis").strip().lower()
        flow_engine, flow_backend = create_visual_cut_flow_engine(cv2_mod, backend_preference=backend_preference)

        payload_cache: dict = {}
        inspected_intervals: set[tuple[int, int]] = set()
        left_payload = self._scan_prepare_visual_frame_payload(start_frame, max_width=coarse_width, cache=payload_cache)
        if not left_payload:
            return None

        def _inspect_candidate(candidate: dict, *, reason: str) -> dict | None:
            interval_start = int(candidate.get("interval_start_frame", candidate.get("boundary_frame", 0)) or 0)
            interval_end = int(candidate.get("interval_end_frame", interval_start + coarse_stride) or (interval_start + coarse_stride))
            interval_key = (interval_start, interval_end)
            if interval_key in inspected_intervals:
                return None
            inspected_intervals.add(interval_key)

            window_start = max(0, interval_start - interval_margin)
            window_end = max(window_start + 1, interval_end + interval_margin)
            fine_candidate = self._scan_find_live_visual_cut_in_window(
                window_start,
                window_end,
                analysis_width=fine_width,
                direction=direction_i,
                payload_cache=payload_cache,
                coarse_history=[candidate],
            )
            if not isinstance(fine_candidate, dict):
                print(
                    f"↪️ [scan-cut-live] window reject {window_start}-{window_end} "
                    f"seed={interval_start}-{interval_end} seed_score={float(candidate.get('score', 0.0) or 0.0):.2f} "
                    f"reason={reason}",
                    flush=True,
                )
                return None

            refined = self._scan_refine_live_visual_cut(fine_candidate, coarse_history=[candidate])
            print(
                f"🎯 [scan-cut-live] CUT dir={direction_i} "
                f"frame={int(refined.get('boundary_frame', interval_start) or interval_start)} "
                f"sec={float(refined.get('boundary_sec', 0.0) or 0.0):.3f}s "
                f"score={float(refined.get('score', 0.0) or 0.0):.3f} "
                f"edge_res={float(refined.get('edge_residual', 0.0) or 0.0):.4f} "
                f"edge_diff={float(refined.get('edge_diff', 0.0) or 0.0):.4f} "
                f"motion={float(refined.get('mean_motion_px', 0.0) or 0.0):.2f} "
                f"coh={float(refined.get('coherence', 0.0) or 0.0):.3f} "
                f"seed={interval_start}-{interval_end} reason={reason}",
                flush=True,
            )
            return refined

        def _build_dense_flow_coarse_scan():
            dense_raw_history: list[dict] = []
            dense_series: list[dict] = []
            dense_candidates: list[dict] = []
            for idx in range(1, len(sparse_payloads)):
                right_payload = sparse_payloads[idx]
                if direction_i > 0:
                    pair_left = sparse_payloads[idx - 1]
                    pair_right = right_payload
                else:
                    pair_left = right_payload
                    pair_right = sparse_payloads[idx - 1]

                metric = visual_cut_pair_metrics(
                    pair_left,
                    pair_right,
                    cv2_mod,
                    flow_engine=flow_engine,
                    backend_preference=backend_preference,
                )
                if not isinstance(metric, dict):
                    continue
                metric.update(
                    {
                        "boundary_frame": int(pair_left["global_frame"]),
                        "boundary_sec": float(pair_left["global_sec"]),
                        "left_frame": int(pair_left["global_frame"]),
                        "right_frame": int(pair_right["global_frame"]),
                        "analysis_width": int(coarse_width),
                        "flow_backend": str(flow_backend),
                        "source_changed": bool(pair_left.get("source_path") != pair_right.get("source_path")),
                        "interval_start_frame": int(min(pair_left["global_frame"], pair_right["global_frame"])),
                        "interval_end_frame": int(max(pair_left["global_frame"], pair_right["global_frame"])),
                        "interval_stride_frames": int(abs(int(pair_right["global_frame"]) - int(pair_left["global_frame"]))),
                    }
                )
                dense_raw_history.append(metric)
                history = dense_raw_history[-8:-1]
                scored = score_visual_cut_metrics(metric, history=history, settings=settings)
                if not isinstance(scored, dict):
                    continue
                coarse_item = {
                    **metric,
                    **scored,
                    "direction": int(direction_i),
                }
                dense_series.append(coarse_item)
                if float(coarse_item.get("score", 0.0) or 0.0) >= candidate_min_score:
                    dense_candidates.append(coarse_item)
            return dense_series, dense_candidates

        coarse_steps = max(1, int(math.ceil(float(coarse_max_frames) / max(float(coarse_stride), 1.0))))
        sparse_payloads: list[dict] = [left_payload]
        for step_idx in range(1, coarse_steps + 1):
            right_frame = start_frame + (direction_i * coarse_stride * step_idx)
            if right_frame < 0:
                break
            right_payload = self._scan_prepare_visual_frame_payload(right_frame, max_width=coarse_width, cache=payload_cache)
            if not right_payload:
                break
            sparse_payloads.append(right_payload)

        native_coarse_used = False
        raw_history: list[dict] = []
        coarse_series: list[dict] = []
        coarse_candidates: list[dict] = []
        if self._scan_live_native_coarse_enabled():
            try:
                native_series = native_visual_cut_coarse_series(
                    sparse_payloads,
                    region_threshold=float(settings.get("scan_cut_live_native_coarse_region_threshold", 24.0) or 24.0),
                    diff_threshold=float(settings.get("scan_cut_live_native_coarse_diff_threshold", 32.0) or 32.0),
                )
            except Exception:
                native_series = None
            if isinstance(native_series, list) and native_series:
                native_coarse_used = True
                for metric in native_series:
                    if not isinstance(metric, dict):
                        continue
                    metric = dict(metric)
                    metric["flow_backend"] = "native_edge_series"
                    raw_history.append(metric)
                    history = raw_history[-8:-1]
                    scored = score_visual_cut_coarse_metrics(metric, history=history, settings=settings)
                    if not isinstance(scored, dict):
                        continue
                    coarse_item = {
                        **metric,
                        **scored,
                        "direction": int(direction_i),
                    }
                    coarse_series.append(coarse_item)
                    if float(coarse_item.get("score", 0.0) or 0.0) >= candidate_min_score:
                        coarse_candidates.append(coarse_item)

        def _inspect_coarse_candidates(series: list[dict], candidates: list[dict], *, backend_label: str, inspect_cap: int | None = None):
            for idx in range(1, max(1, len(series) - 1)):
                if idx + 1 >= len(series):
                    break
                prev_item = series[idx - 1]
                current_item = series[idx]
                next_item = series[idx + 1]
                if self._scan_is_live_visual_coarse_peak(
                    prev_item,
                    current_item,
                    next_item,
                    min_score=candidate_min_score,
                ):
                    refined = _inspect_candidate(current_item, reason="coarse_peak")
                    if isinstance(refined, dict):
                        return refined

            selected_candidates = self._scan_select_live_visual_candidates(
                candidates,
                stride_frames=coarse_stride,
                top_k=(max(candidate_topk, 10) if backend_label == "cpp_native" else candidate_topk),
            )
            if not selected_candidates:
                return None

            ordered_candidates = sorted(
                list(selected_candidates or []),
                key=lambda item: int(item.get("interval_start_frame", item.get("boundary_frame", 0)) or 0),
                reverse=direction_i < 0,
            )
            print(
                f"🔎 [scan-cut-live] COARSE dir={direction_i} "
                f"search_frames={coarse_max_frames} stride={coarse_stride} width={coarse_width} "
                f"backend={backend_label} "
                f"candidates="
                + ", ".join(
                    f"{int(item.get('interval_start_frame', 0) or 0)}-{int(item.get('interval_end_frame', 0) or 0)}"
                    f"@{float(item.get('score', 0.0) or 0.0):.2f}"
                    for item in list(ordered_candidates or [])
                ),
                flush=True,
            )
            limit = len(ordered_candidates) if inspect_cap is None else max(1, min(len(ordered_candidates), int(inspect_cap)))
            for candidate in list(ordered_candidates or [])[:limit]:
                refined = _inspect_candidate(candidate, reason="coarse_fallback")
                if isinstance(refined, dict):
                    return refined
            return None

        if native_coarse_used:
            refined = _inspect_coarse_candidates(
                coarse_series,
                coarse_candidates,
                backend_label="cpp_native",
                inspect_cap=max(2, min(4, candidate_topk)),
            )
            if isinstance(refined, dict):
                return refined
            print("↪️ [scan-cut-live] native coarse miss -> dense flow fallback", flush=True)

        coarse_series, coarse_candidates = _build_dense_flow_coarse_scan()
        refined = _inspect_coarse_candidates(
            coarse_series,
            coarse_candidates,
            backend_label=str(flow_backend),
        )
        if isinstance(refined, dict):
            return refined

        return None

    def _scan_jump_to_live_visual_cut(self, direction: int) -> bool:
        candidate = self._scan_find_live_visual_cut(direction)
        if not isinstance(candidate, dict):
            return False
        candidate = self._scan_verify_live_visual_candidate(candidate, direction=direction)
        if not isinstance(candidate, dict):
            return False

        try:
            target_sec = self._snap_to_frame(float(candidate.get("boundary_sec", 0.0) or 0.0))
        except Exception:
            return False
        if target_sec < 0.0:
            return False

        try:
            if hasattr(self.video_player, "pause_video"):
                self.video_player.pause_video()
        except Exception:
            pass

        self._set_scan_cut_button_active(direction)
        try:
            self._scan_preview_global_sec(target_sec)
        except Exception:
            timeline = getattr(self, "timeline", None)
            if timeline is not None:
                try:
                    timeline.set_playhead(target_sec)
                except Exception:
                    pass
        try:
            self._scan_show_cut_thumbnail(target_sec)
        except Exception:
            pass

        try:
            if hasattr(self.video_player, "info_label"):
                if bool(candidate.get("follower_verified")):
                    self.video_player.info_label.setText(
                        f"실화면 컷 정지 · 후발대 {str(candidate.get('follower_verified_mode', 'strict_verify') or 'strict_verify')}"
                    )
                else:
                    self.video_player.info_label.setText(
                        f"실화면 컷 정지 · score {float(candidate.get('score', 0.0) or 0.0):.2f}"
                    )
        except Exception:
            pass

        try:
            QTimer.singleShot(120, lambda: self._set_scan_cut_button_active(0))
        except Exception:
            self._set_scan_cut_button_active(0)

        return True


    def _scan_cached_cut_jump_enabled(self) -> bool:
        settings = getattr(self, "settings", {}) or {}
        raw = settings.get("scan_cut_cached_jump_enabled", True)
        if isinstance(raw, str):
            return raw.strip().lower() not in {"0", "false", "no", "off", "미사용"}
        return bool(raw)

    def _scan_fast_boundary_sources(self) -> list:
        rows: list = []

        def _extend(values) -> None:
            if not values:
                return
            try:
                rows.extend(list(values))
            except Exception:
                pass

        timeline = getattr(self, "timeline", None)
        canvas = getattr(timeline, "canvas", None)
        if canvas is not None:
            _extend(getattr(canvas, "boundary_times", []) or [])
            _extend(getattr(canvas, "scan_boundary_times", []) or [])

        _extend(getattr(self, "_project_boundary_times", []) or [])
        _extend(getattr(self, "_auto_cut_boundary_scan_lines", []) or [])

        for obj in (self.window() if hasattr(self, "window") else None, getattr(self, "parent", lambda: None)()):
            if obj is None:
                continue
            _extend(getattr(obj, "_project_boundary_times", []) or [])
            _extend(getattr(obj, "_auto_cut_boundary_scan_lines", []) or [])

        return rows

    def _scan_jump_to_cached_cut_boundary(self, direction: int) -> bool:
        """
        Fast path for the << / >> cut buttons.

        If the project already has confirmed/provisional cut markers, jump with a
        sorted boundary lookup instead of starting the expensive visual scanner.
        """

        if not self._scan_cached_cut_jump_enabled():
            return False

        try:
            fps = float(self._current_frame_fps())
        except Exception:
            fps = 30.0

        timeline = getattr(self, "timeline", None)
        canvas = getattr(timeline, "canvas", None)
        try:
            total_sec = float(getattr(canvas, "total_duration", 0.0) or 0.0) if canvas is not None else 0.0
        except Exception:
            total_sec = 0.0

        rows = self._scan_fast_boundary_sources()
        boundaries = normalize_boundary_seconds(rows, primary_fps=fps, max_sec=total_sec or None)
        if not boundaries:
            return False

        try:
            current_sec = float(self._manual_global_sec_from_player())
        except Exception:
            try:
                current_sec = float(getattr(canvas, "playhead_sec", 0.0) or 0.0)
            except Exception:
                current_sec = 0.0

        try:
            direction_i = 1 if int(direction) > 0 else -1
        except Exception:
            direction_i = 1

        min_gap = max(0.06, min(0.35, 3.0 / max(fps, 1.0)))
        target_sec = nearest_boundary_second(
            boundaries,
            current_sec=current_sec,
            direction=direction_i,
            primary_fps=fps,
            max_sec=total_sec or None,
            min_gap_sec=min_gap,
        )
        if target_sec is None:
            return False

        target_sec = self._snap_to_frame(float(target_sec))
        try:
            if hasattr(self.video_player, "pause_video"):
                self.video_player.pause_video()
        except Exception:
            pass

        self._set_scan_cut_button_active(direction_i)

        try:
            self._scan_preview_global_sec(target_sec)
        except Exception:
            try:
                if timeline is not None:
                    timeline.set_playhead(target_sec)
            except Exception:
                pass

        try:
            if hasattr(self.video_player, "info_label"):
                self.video_player.info_label.setText(f"컷 경계 즉시 이동 · {target_sec:.3f}s")
        except Exception:
            pass

        try:
            QTimer.singleShot(120, lambda: self._set_scan_cut_button_active(0))
        except Exception:
            self._set_scan_cut_button_active(0)

        print(
            f"⚡ [scan-cut-fast-jump] cached boundary dir={direction_i} "
            f"{current_sec:.3f}s -> {target_sec:.3f}s count={len(boundaries)}",
            flush=True,
        )
        return True



    def _on_scan_cut_requested(self, direction: int):
        try:
            scan_enabled = bool((getattr(self, "settings", {}) or {}).get(
                "cut_boundary_detection_enabled",
                (getattr(self, "settings", {}) or {}).get("scan_cut_enabled", True),
            ))
        except Exception:
            scan_enabled = True

        if not scan_enabled:
            try:
                self.video_player.info_label.setText("컷 경계 탐색 미사용")
            except Exception:
                pass
            print("⏭️ [scan-cut] SKIP disabled by cut_boundary_detection_enabled=False", flush=True)
            return

        if not hasattr(self, "video_player"):
            print("🎬 [scan-cut] video_player 없음", flush=True)
            return

        try:
            direction = 1 if int(direction) > 0 else -1
        except Exception:
            direction = 1

        current_state = getattr(self, "_scan_cut_state", None)
        pending_direction = int(getattr(self, "_scan_cut_pending_direction", 0) or 0)
        if current_state:
            active_dir = int(current_state.get("direction", 0) or 0)
            if active_dir == direction:
                self._cancel_scan_cut("same-button-toggle")
                return
            self._cancel_scan_cut("switch-direction", update_label=False)
        elif pending_direction:
            if pending_direction == direction:
                self._cancel_scan_cut("same-button-pending-toggle")
                return
            self._cancel_scan_cut("switch-direction-pending", update_label=False)

        if hasattr(self.video_player, "pause_video"):
            self.video_player.pause_video()

        self._set_scan_cut_button_active(direction)
        try:
            if hasattr(self.video_player, "info_label"):
                self.video_player.info_label.setText("실화면 컷 탐색 준비 중...")
        except Exception:
            pass
        launch_token = object()
        self._scan_cut_pending_direction = int(direction)
        self._scan_cut_launch_token = launch_token

        def _launch_scan() -> None:
            if getattr(self, "_scan_cut_launch_token", None) is not launch_token:
                return
            self._scan_cut_launch_token = None
            self._scan_cut_pending_direction = 0

            try:
                if hasattr(self.video_player, "info_label"):
                    self.video_player.info_label.setText("실화면 컷 탐색 중...")
            except Exception:
                pass

            if self._scan_jump_to_live_visual_cut(direction):
                return

            if self._scan_jump_to_cached_cut_boundary(direction):
                return

            fps = self._current_frame_fps()
            start_sec = self._manual_global_sec_from_player()
            start_frame = max(0, int(round(start_sec * fps)))
            threshold = self._scan_threshold()
            interval = self._scan_interval_ms()
            max_frames = self._scan_max_frames()
            start_image = self._scan_capture_image_at_global(start_sec)

            print(
                f"🎬 [scan-cut] START dir={direction} start_frame={start_frame} "
                f"start={start_frame / fps:.3f}s fps={fps:.3f} threshold={threshold:.2f} "
                f"interval={interval}ms max_frames={max_frames} "
                f"image={self._scan_image_backend_label() if start_image is not None else 'NONE'}",
                flush=True,
            )

            if start_image is None:
                try:
                    self.video_player.info_label.setText("컷 경계 탐색 실패 · 프레임 없음")
                except Exception:
                    pass
                self._set_scan_cut_button_active(0)
                return

            self._scan_cut_state = {
                "direction": direction,
                "last_frame": start_frame,
                "last_image": start_image,
                "frames": 0,
                "threshold": threshold,
                "hard_threshold": self._scan_hard_threshold(),
                "consecutive_hits_required": self._scan_consecutive_hits_required(),
                "consecutive_hits": 0,
                "first_hit_frame": None,
                "first_hit_sec": None,
                "max_frames": max_frames,
                "busy": False,
            }

            if not hasattr(self, "_scan_cut_timer"):
                self._scan_cut_timer = QTimer(self)
                self._scan_cut_timer.timeout.connect(self._scan_cut_tick)

            try:
                self.video_player.info_label.setText("컷 경계 탐색 중...")
            except Exception:
                pass

            self._scan_set_timeline_input_locked(True)
            self._scan_cut_timer.stop()
            self._scan_cut_timer.setInterval(interval)
            self._scan_cut_timer.start()

        try:
            QTimer.singleShot(0, _launch_scan)
        except Exception:
            _launch_scan()




    def _scan_show_cut_thumbnail(self, global_sec: float) -> None:
        """
        컷 경계 확정 후 해당 컷 직전 프레임을 비디오 화면에 썸네일로 고정 표시한다.
        """
        try:
            global_sec = self._snap_to_frame(float(global_sec))
        except Exception:
            return

        try:
            if self._scan_show_fast_thumbnail_at_global(global_sec):
                print(f"🖼️ [scan-cut] thumbnail shown fast global={global_sec:.3f}s", flush=True)
                return
        except Exception:
            pass

        # fallback
        try:
            self._scan_preview_global_sec(global_sec)
        except Exception:
            pass


    def _project_file_for_cut_boundary_save(self) -> str:
        """
        현재 에디터가 연결된 프로젝트 JSON 경로를 최대한 안전하게 찾는다.
        프로젝트가 없으면 빈 문자열을 반환한다.
        """
        candidates = [
            "project_file",
            "project_path",
            "_project_file",
            "_project_path",
            "current_project_file",
            "current_project_path",
        ]

        for obj in (self, self.window() if hasattr(self, "window") else None):
            if obj is None:
                continue
            for attr in candidates:
                try:
                    value = str(getattr(obj, attr, "") or "")
                except Exception:
                    value = ""
                if value and value.endswith(".json") and os.path.exists(value):
                    return value

        try:
            state = getattr(self, "project_state", None) or getattr(self, "_project_state", None)
            if isinstance(state, dict):
                for key in ("path", "project_file", "project_path"):
                    value = str(state.get(key, "") or "")
                    if value and value.endswith(".json") and os.path.exists(value):
                        return value
        except Exception:
            pass

        return ""

    def _scan_cut_source_context(self, global_sec: float) -> dict:
        try:
            if hasattr(self, "_scan_get_context_for_global_sec"):
                ctx = self._scan_get_context_for_global_sec(float(global_sec))
                if isinstance(ctx, dict):
                    return dict(ctx)
        except Exception:
            pass
        try:
            if hasattr(self, "_resolve_active_context"):
                ctx = self._resolve_active_context(global_sec=float(global_sec))
                if isinstance(ctx, dict):
                    return dict(ctx)
        except Exception:
            pass
        return {}

    def _save_cut_boundary_to_project(self, global_sec: float, frame: int | None = None, score: float | None = None, regions: int | None = None, reason: str = "manual_scan") -> None:
        """
        scan-cut으로 찾은 컷 경계를 프로젝트 JSON의 analysis.cut_boundaries에 누적 저장한다.

        저장 위치:
        project["analysis"]["cut_boundaries"]
        """
        project_path = self._project_file_for_cut_boundary_save()
        if not project_path:
            try:
                print("⚠️ [scan-cut] 프로젝트 파일 경로를 찾지 못해 컷 경계를 JSON에 저장하지 못했습니다.", flush=True)
            except Exception:
                pass
            return

        try:
            global_sec = self._snap_to_frame(float(global_sec))
        except Exception:
            global_sec = float(global_sec or 0.0)

        try:
            fps = self._current_frame_fps()
        except Exception:
            fps = 30.0

        if frame is None:
            try:
                frame = int(round(global_sec * fps))
            except Exception:
                frame = 0

        ctx = self._scan_cut_source_context(global_sec)

        try:
            source_path = str(ctx.get("clip_file", "") or ctx.get("source_path", "") or "")
            local_sec = float(ctx.get("local_sec", global_sec) or global_sec)
            clip_idx = int(ctx.get("clip_idx", 0) or 0)
        except Exception:
            source_path = ""
            local_sec = global_sec
            clip_idx = 0

        record = {
            "schema": "cut_boundary.v1",
            "id": f"cut_{int(frame):08d}",
            "time": global_sec,
            "timeline_sec": global_sec,
            "frame": int(frame),
            "timeline_frame": int(frame),
            "fps": float(fps),
            "clip_idx": clip_idx,
            "clip_local_sec": local_sec,
            "source_path": source_path,
            "score": None if score is None else float(score),
            "regions": None if regions is None else int(regions),
            "reason": str(reason or "manual_scan"),
            "detector": "opencv-gray-pyramid60",
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }

        try:
            from core.project.project_io import read_project_file, write_project_file

            project = read_project_file(project_path)
        except Exception as exc:
            print(f"⚠️ [scan-cut] 프로젝트 파일 읽기 실패: {exc}", flush=True)
            return

        analysis = project.setdefault("analysis", {})
        analysis["cut_boundary_schema"] = "cut_boundaries.v1"
        boundaries = analysis.setdefault("cut_boundaries", [])

        # 같은 frame 근처 중복 저장 방지
        replaced = False
        for idx, item in enumerate(list(boundaries)):
            try:
                old_frame = int(item.get("timeline_frame", item.get("frame", -999999)) or -999999)
            except Exception:
                old_frame = -999999
            if abs(old_frame - int(frame)) <= 1:
                boundaries[idx] = record
                replaced = True
                break

        if not replaced:
            boundaries.append(record)

        boundaries.sort(key=lambda item: float(item.get("timeline_sec", item.get("time", 0.0)) or 0.0))

        analysis["cut_boundary_settings"] = {
            "enabled": True,
            "detector": "opencv-gray-pyramid60",
            "count": len(boundaries),
            "absolute": True,
            "locked": True,
        }

        try:
            sync_project_cut_boundaries(
                project,
                settings=getattr(self, "settings", {}) or {},
                primary_fps=fps,
            )
        except Exception as exc:
            print(f"⚠️ [scan-cut] 컷 경계 editor_state 동기화 실패: {exc}", flush=True)

        project["updated_at"] = datetime.now().isoformat()

        try:
            write_project_file(project_path, project)
            print(
                f"💾 [scan-cut] project cut boundary saved frame={frame} time={global_sec:.3f}s count={len(boundaries)}",
                flush=True,
            )
        except Exception as exc:
            print(f"⚠️ [scan-cut] 프로젝트 컷 경계 저장 실패: {exc}", flush=True)


    def _scan_cut_tick(self):
        state = getattr(self, "_scan_cut_state", None)
        if not state:
            if hasattr(self, "_scan_cut_timer"):
                self._scan_cut_timer.stop()
            return

        if bool(state.get("busy")):
            return

        state["busy"] = True

        try:
            fps = self._current_frame_fps()
            direction = int(state.get("direction", 1) or 1)
            threshold = float(state.get("threshold", 24.0) or 24.0)
            hard_threshold = float(state.get("hard_threshold", 45.0) or 45.0)
            consecutive_required = int(state.get("consecutive_hits_required", 2) or 2)
            max_frames = int(state.get("max_frames", 0) or 0)
            frames_per_tick = self._scan_frames_per_tick()
            preview_every = self._scan_preview_every_frames()
            required_regions = self._scan_cross_regions_required()

            for _ in range(frames_per_tick):
                last_frame = max(0, int(state.get("last_frame", 0) or 0))
                next_frame = max(0, last_frame + direction)
                last_sec = last_frame / fps
                next_sec = next_frame / fps
                frame_count = int(state.get("frames", 0) or 0)

                if next_frame == last_frame or (max_frames > 0 and frame_count >= max_frames):
                    self._scan_cut_timer.stop()
                    self._scan_cut_state = None
                    self._set_scan_cut_button_active(0)
                    self._scan_set_timeline_input_locked(False)
                    self._scan_preview_global_sec(last_sec)
                    return

                if hasattr(self, "_scan_same_source") and not self._scan_same_source(last_sec, next_sec):
                    self._scan_cut_timer.stop()
                    self._scan_cut_state = None
                    self._set_scan_cut_button_active(0)
                    self._scan_set_timeline_input_locked(False)
                    self._scan_preview_global_sec(last_sec)
                    self._scan_show_cut_thumbnail(last_sec)  # SCAN_THUMBNAIL_ON_BOUNDARY_PATCH
                    print(f"🛑 [scan-cut] CLIP BOUNDARY stop_frame={last_frame} stop={last_sec:.3f}s", flush=True)
                    return

                prev_image = state.get("last_image") or self._scan_capture_image_at_global(last_sec)
                next_image = self._scan_capture_image_at_global(next_sec)
                score = self._scan_image_delta(prev_image, next_image)
                region_hits = int(getattr(self, "_scan_last_region_hits", 0) or 0)
                region_deltas = list(getattr(self, "_scan_last_region_deltas", []) or [])
                new_count = frame_count + 1

                if new_count == 1 or new_count % preview_every == 0:
                    self._scan_preview_global_sec(next_sec)

                is_hard_cut = score >= hard_threshold and region_hits >= max(1, min(2, required_regions))
                is_soft_hit = score >= threshold and region_hits >= required_regions

                consecutive_hits = int(state.get("consecutive_hits", 0) or 0)
                if is_soft_hit:
                    if consecutive_hits <= 0:
                        state["first_hit_frame"] = last_frame
                        state["first_hit_sec"] = last_sec
                    consecutive_hits += 1
                else:
                    consecutive_hits = 0
                    state["first_hit_frame"] = None
                    state["first_hit_sec"] = None

                state["consecutive_hits"] = consecutive_hits

                if new_count == 1 or new_count % 30 == 0 or is_soft_hit or is_hard_cut:
                    delta_text = ",".join(f"{d:.1f}" for d in region_deltas[:5])
                    print(
                        f"📊 [scan-cut] frame={new_count} delta={score:.2f}/{threshold:.2f} "
                        f"regions={region_hits}/{required_regions} hit={consecutive_hits}/{consecutive_required} "
                        f"frame {last_frame}->{next_frame} {last_sec:.3f}s->{next_sec:.3f}s "
                        f"img={self._scan_image_backend_label() if next_image is not None else 'NONE'} "
                        f"cross=[{delta_text}]",
                        flush=True,
                    )

                if next_image is None:
                    self._scan_cut_timer.stop()
                    self._scan_cut_state = None
                    self._set_scan_cut_button_active(0)
                    self._scan_set_timeline_input_locked(False)
                    self._scan_preview_global_sec(last_sec)
                    return

                if is_hard_cut or consecutive_hits >= consecutive_required:
                    stop_frame = last_frame
                    stop_sec = last_sec
                    if not is_hard_cut:
                        stop_frame = int(state.get("first_hit_frame", last_frame) or last_frame)
                        stop_sec = float(state.get("first_hit_sec", last_sec) or last_sec)

                    self._scan_cut_timer.stop()
                    self._scan_cut_state = None
                    self._set_scan_cut_button_active(0)
                    self._scan_set_timeline_input_locked(False)
                    self._scan_preview_global_sec(stop_sec)
                    self._scan_show_cut_thumbnail(stop_sec)

                    reason = "hard" if is_hard_cut else f"{consecutive_hits}/{consecutive_required}"
                    print(
                        f"🛑 [scan-cut] CUT FOUND reason={reason} stop_frame={stop_frame} "
                        f"stop={stop_sec:.3f}s delta={score:.2f} regions={region_hits}/{required_regions}",
                        flush=True,
                    )
                    try:
                        self.video_player.info_label.setText(f"컷 경계 정지 · 변화량 {score:.1f}")
                    except Exception:
                        pass
                    return

                state["last_frame"] = next_frame
                state["last_image"] = next_image
                state["frames"] = new_count
                state["busy"] = False

        except Exception as exc:
            try:
                self._scan_cut_timer.stop()
            except Exception:
                pass
            self._scan_cut_state = None
            self._set_scan_cut_button_active(0)
            self._scan_set_timeline_input_locked(False)
            print(f"❌ [scan-cut] tick error: {exc}", flush=True)
        finally:
            state = getattr(self, "_scan_cut_state", None)
            if state:
                state["busy"] = False

    def _scan_cut_after_seek(self, next_frame):
        state = getattr(self, "_scan_cut_state", None)
        if not state:
            print("🎬 [scan-cut] after-seek skipped no-state", flush=True)
            return

        fps = self._current_frame_fps()
        next_frame = max(0, int(next_frame or 0))
        prev_frame = max(0, int(state.get("probe_prev_frame", state.get("last_frame", next_frame)) or 0))
        prev_sec = prev_frame / fps
        next_sec = next_frame / fps

        next_image = self._scan_capture_image(next_sec)
        prev_image = state.get("last_image")
        score = self._scan_image_delta(prev_image, next_image)
        threshold = float(state.get("threshold", 12.0) or 12.0)
        frame_count = int(state.get("frames", 0) or 0) + 1

        if frame_count == 1 or frame_count % 30 == 0 or score >= threshold:
            print(
                f"📊 [scan-cut] frame={frame_count} delta={score:.2f}/{threshold:.2f} "
                f"frame {prev_frame}->{next_frame} {prev_sec:.3f}s->{next_sec:.3f}s "
                f"img={(next_image.get('kind') if isinstance(next_image, dict) else ('QIMAGE' if next_image is not None else 'NONE'))}",
                flush=True,
            )

        if score >= threshold:
            if hasattr(self, "_scan_cut_timer"):
                self._scan_cut_timer.stop()
            self._scan_cut_state = None
            self._set_scan_cut_button_active(0)
            self._seek_global_exact(prev_sec)
            self._sync_after_manual_seek(prev_sec)
            print(f"🛑 [scan-cut] CUT FOUND stop_frame={prev_frame} stop={prev_sec:.3f}s delta={score:.2f}", flush=True)
            try:
                self.video_player.info_label.setText(f"컷 경계 정지 · 변화량 {score:.1f}")
            except Exception:
                pass
            return

        state["last_frame"] = next_frame
        state["last_image"] = next_image
        state["frames"] = frame_count
        state["busy"] = False
