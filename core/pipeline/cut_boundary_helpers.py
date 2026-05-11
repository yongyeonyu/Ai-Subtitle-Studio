# Version: 03.14.29
# Phase: PHASE1-B
"""
core/pipeline/cut_boundary_helpers.py
PipelineCutBoundaryMixin — 컷 경계 자동 분석 · 캐시 · 주제없음 플레이스홀더 · 분할/스냅 헬퍼
"""
import json
import os
import queue
import threading
import time

from core.autopilot_policy import apply_autopilot_runtime_policy, hybrid_cut_boundary_decision
from core.cut_boundary_api import CUT_BOUNDARY_ALGORITHM_ID, CUT_BOUNDARY_ALGORITHM_VERSION, CUT_BOUNDARY_API_VERSION
from core.cut_boundary_audio import AUDIO_GAIN_LINE_COLOR, is_audio_gain_boundary
from core.cut_boundary_native_plan import (
    build_middle_segments_for_stage,
    build_follower_native_verify_settings,
    build_provisional_native_settings,
    checked_provisional_boundary_row,
    provisional_boundary_row,
    reviewed_middle_source_rows,
)
from core.media_fingerprint import media_fingerprint_digest
from core.pipeline.cut_boundary_prescan_policy import (
    cut_boundary_adaptive_prescan_plan,
    fast_cut_boundary_prescan_settings,
)
from core.project.project_io import read_project_file, write_project_file
from core.runtime.logger import get_logger
from core.settings import load_settings


def _truthy_setting(value, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"", "auto"}:
            return bool(default)
        return lowered not in {"0", "false", "no", "off", "미사용", "사용안함", "disabled"}
    return bool(value)


class PipelineCutBoundaryMixin:
    """Pipeline 컷 경계 분석/캐시/적용 헬퍼 모음."""

    def _cut_boundary_snapshot_for_pipeline(self, *, force_reload: bool = False) -> dict:
        """Return cached cut-boundary/provisional rows for the current project.

        Full subtitle generation calls these helpers many times from preview,
        STT, LLM, and final post-process paths. Re-reading the project JSON on
        each call creates avoidable I/O and jitter, so we cache by
        project-path/mtime plus provisional in-memory fallback signature.
        """
        provisional_fallback = [dict(item) for item in list(getattr(self, "_cut_boundary_provisional_rows", []) or [])]
        try:
            provisional_signature = json.dumps(
                provisional_fallback,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except Exception:
            provisional_signature = str(len(provisional_fallback))

        ui = getattr(self, "ui", None)
        project_path = str(getattr(ui, "_current_project_path", "") or "")
        mtime_ns = None
        if project_path and os.path.exists(project_path):
            try:
                st = os.stat(project_path)
                mtime_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000)))
            except Exception:
                mtime_ns = None

        cache = getattr(self, "_cut_boundary_pipeline_cache", None)
        if (
            not force_reload
            and isinstance(cache, dict)
            and cache.get("project_path") == project_path
            and cache.get("mtime_ns") == mtime_ns
            and cache.get("provisional_signature") == provisional_signature
        ):
            return {
                "cut_boundaries": [dict(item) for item in list(cache.get("cut_boundaries", []) or [])],
                "provisional_cut_boundaries": [dict(item) for item in list(cache.get("provisional_cut_boundaries", []) or [])],
            }

        cut_rows: list[dict] = []
        provisional_rows: list[dict] = provisional_fallback
        try:
            from core.cut_boundary import project_cut_boundaries, project_cut_provisional_boundaries

            if project_path and os.path.exists(project_path):
                project = read_project_file(project_path)
                cut_rows = [dict(item) for item in list(project_cut_boundaries(project) or [])]
                project_provisional = [dict(item) for item in list(project_cut_provisional_boundaries(project) or [])]
                if project_provisional:
                    provisional_rows = project_provisional
        except Exception:
            cut_rows = []
            provisional_rows = provisional_fallback

        snapshot = {
            "project_path": project_path,
            "mtime_ns": mtime_ns,
            "provisional_signature": provisional_signature,
            "cut_boundaries": [dict(item) for item in cut_rows],
            "provisional_cut_boundaries": [dict(item) for item in provisional_rows],
        }
        self._cut_boundary_pipeline_cache = snapshot
        return {
            "cut_boundaries": [dict(item) for item in cut_rows],
            "provisional_cut_boundaries": [dict(item) for item in provisional_rows],
        }

    def _project_cut_boundaries_for_pipeline(self) -> list[dict]:
        """Return saved visual cut boundaries from the current project file."""
        try:
            return list(self._cut_boundary_snapshot_for_pipeline().get("cut_boundaries", []) or [])
        except Exception:
            return []

    def _project_provisional_cut_boundaries_for_pipeline(self) -> list[dict]:
        try:
            return list(self._cut_boundary_snapshot_for_pipeline().get("provisional_cut_boundaries", []) or [])
        except Exception:
            return [dict(item) for item in list(getattr(self, "_cut_boundary_provisional_rows", []) or [])]

    def _project_cut_provisional_boundaries_for_pipeline(self) -> list[dict]:
        """Backward-compatible alias for provisional cut-boundary rows."""
        return self._project_provisional_cut_boundaries_for_pipeline()

    def _clear_completed_cut_boundary_provisionals(
        self,
        project_path: str = "",
        *,
        settings: dict | None = None,
        detected: list[dict] | None = None,
        reviewed_rows: list[dict] | None = None,
        emit: bool = True,
    ) -> None:
        """Remove temporary cut-boundary rows after follower verification finishes.

        Provisional rows are useful while the pioneer/follower workers are
        running, but once the follower has finished they must not remain in the
        project file. Otherwise a later project refresh can resurrect gray
        dotted "temporary" lines even though final cut boundaries are done.
        """
        try:
            self._cut_boundary_provisional_rows = []
        except Exception:
            pass
        try:
            self._cut_boundary_pipeline_cache = None
        except Exception:
            pass
        if emit:
            try:
                self._ui_emit("_sig_preview_cut_boundary_scan_lines", [])
            except Exception:
                pass

        path = str(project_path or getattr(getattr(self, "ui", None), "_current_project_path", "") or "")
        if not path or not os.path.exists(path):
            return

        try:
            from core.cut_boundary import normalize_cut_boundaries, sync_project_cut_boundaries

            project = read_project_file(path)
            analysis = project.setdefault("analysis", {})
            if detected is not None:
                analysis["cut_boundaries"] = normalize_cut_boundaries(list(detected or []))
            if reviewed_rows is not None:
                analysis["cut_boundary_reviewed_rows"] = normalize_cut_boundaries(list(reviewed_rows or []))
            analysis["cut_boundary_provisional_boundaries"] = []
            sync_project_cut_boundaries(
                project,
                settings=settings if settings is not None else project.get("user_settings", {}),
                provisional_boundaries=[],
            )
            write_project_file(path, project)
        except Exception as exc:
            get_logger().log(f"  ⚠️ [컷 경계] 완료 임시선 정리 저장 실패: {exc}")

    def _cut_boundary_cache_settings_payload(self, settings: dict) -> dict:
        settings = dict(settings or {})
        try:
            duration_sec = max(0.0, float(settings.get("cut_boundary_media_duration_sec", 0.0) or 0.0))
        except Exception:
            duration_sec = 0.0
        duration_bucket = int(duration_sec // 300.0 * 300.0) if duration_sec > 0.0 else 0
        return {
            "scan_cut_auto_sample_step_sec": settings.get("scan_cut_auto_sample_step_sec", 2.0),
            "scan_cut_auto_threshold": settings.get("scan_cut_auto_threshold", settings.get("scan_cut_threshold", 24.0)),
            "scan_cut_threshold": settings.get("scan_cut_threshold", 24.0),
            "scan_cut_mode": settings.get("scan_cut_mode", ""),
            "scan_cut_boundary_level": settings.get("scan_cut_boundary_level", settings.get("cut_boundary_level", "medium")),
            "scan_cut_boundary_resolved_level": settings.get("scan_cut_boundary_resolved_level", ""),
            "scan_cut_boundary_resolved_mask": settings.get("scan_cut_boundary_resolved_mask", ""),
            "scan_cut_boundary_provisional_level": settings.get("scan_cut_boundary_provisional_level", ""),
            "scan_cut_boundary_provisional_mask": settings.get("scan_cut_boundary_provisional_mask", ""),
            "cut_boundary_auto_long_media_sec": settings.get("cut_boundary_auto_long_media_sec", 15.0 * 60.0),
            "cut_boundary_auto_short_media_sec": settings.get("cut_boundary_auto_short_media_sec", 10.0 * 60.0),
            "cut_boundary_media_duration_bucket_sec": duration_bucket,
            "cut_boundary_adaptive_level_enabled": bool(settings.get("cut_boundary_adaptive_level_enabled", False)),
            "scan_cut_grid_mask": settings.get("scan_cut_grid_mask", ""),
            "scan_cut_compare_max_width": settings.get("scan_cut_compare_max_width", 1920),
            "scan_cut_compare_max_height": settings.get("scan_cut_compare_max_height", 1080),
            "scan_cut_follower_deferred_until_pioneer_done": bool(settings.get("scan_cut_follower_deferred_until_pioneer_done", False)),
            "scan_cut_follower_stream_start_percent": settings.get("scan_cut_follower_stream_start_percent", 25),
            "scan_cut_follower_stream_batch_size": settings.get("scan_cut_follower_stream_batch_size", 16),
            "scan_cut_follower_verify_micro_batch_max": settings.get("scan_cut_follower_verify_micro_batch_max", 16),
            "scan_cut_realtime_preview_enabled": _truthy_setting(settings.get("scan_cut_realtime_preview_enabled"), True),
            "scan_cut_audio_gain_enabled": settings.get("scan_cut_audio_gain_enabled", True),
            "scan_cut_audio_gain_threshold_db": settings.get("scan_cut_audio_gain_threshold_db", 10.0),
            "scan_cut_audio_gain_window_sec": settings.get("scan_cut_audio_gain_window_sec", None),
            "scan_cut_audio_gain_min_gap_sec": settings.get("scan_cut_audio_gain_min_gap_sec", None),
        }

    def _cut_boundary_cache_path_for_start(self, files: list[str], settings: dict) -> str:
        """Return reusable cut-boundary cache path for the current media/settings."""
        import hashlib
        try:
            from core.runtime import config
            cache_root = os.path.join(config.OUTPUT_DIR, "cut_boundary_cache")
        except Exception:
            cache_root = os.path.join("output", "cut_boundary_cache")

        os.makedirs(cache_root, exist_ok=True)

        payload = {
            "version": 7,
            "cut_boundary_api_version": CUT_BOUNDARY_API_VERSION,
            "cut_boundary_algorithm_version": CUT_BOUNDARY_ALGORITHM_VERSION,
            "cut_boundary_algorithm_id": CUT_BOUNDARY_ALGORITHM_ID,
            "files": [],
            "settings": self._cut_boundary_cache_settings_payload(settings),
        }

        for p in list(files or []):
            try:
                st = os.stat(p)
                payload["files"].append({
                    "path": os.path.abspath(p),
                    "size": int(st.st_size),
                    "mtime_ns": int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))),
                    "fingerprint_digest": media_fingerprint_digest(p, sample_bytes=256 * 1024, include_samples=True),
                })
            except Exception:
                payload["files"].append({
                    "path": os.path.abspath(str(p)),
                    "size": 0,
                    "mtime_ns": 0,
                    "fingerprint_digest": "",
                })

        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        key = hashlib.sha256(raw).hexdigest()[:24]
        return os.path.join(cache_root, f"cut_boundaries_{key}.json")

    def _load_cut_boundary_cache_for_start(self, project_path: str, files: list[str], settings: dict) -> list[dict] | None:
        """Load cached cut boundaries and hydrate only project.analysis.cut_boundaries.

        IMPORTANT:
        - Never replace/move/copy the project file itself.
        - Only inject cached analysis.cut_boundaries into the current project.
        """
        try:
            from core.cut_boundary import normalize_cut_boundaries, sync_project_cut_boundaries

            if bool(getattr(self, "_force_cut_boundary_rescan_once", False)):
                try:
                    self._force_cut_boundary_rescan_once = False
                except Exception:
                    pass
                get_logger().log("  🔄 [컷 경계] 재시작 요청으로 캐시를 건너뛰고 음성/임시/후발대를 다시 분석합니다")
                return None

            cache_path = self._cut_boundary_cache_path_for_start(files, settings)
            if not os.path.exists(cache_path):
                return None

            with open(cache_path, "r", encoding="utf-8") as f:
                payload = json.load(f)

            analysis = payload.get("analysis", {}) if isinstance(payload, dict) else {}
            has_cache_rows = isinstance(analysis, dict) and "cut_boundaries" in analysis
            has_cache_rows = has_cache_rows or (isinstance(payload, dict) and "cut_boundaries" in payload)
            payload_cache_type = str(payload.get("cache_type") or "") if isinstance(payload, dict) else ""
            if not has_cache_rows and payload_cache_type != "cut_boundaries_only":
                return None
            rows = analysis.get("cut_boundaries", [])

            # Backward compatibility with older cache format
            if not rows:
                rows = payload.get("cut_boundaries", []) if isinstance(payload, dict) else []

            rows = normalize_cut_boundaries(rows or [])
            if not rows:
                get_logger().log(
                    f"  ♻️ [컷 경계] 빈 캐시는 완료 결과로 재사용하지 않습니다: {cache_path}"
                )
                if project_path and os.path.exists(project_path):
                    try:
                        project = read_project_file(project_path)
                        analysis = project.setdefault("analysis", {})
                        if (
                            str(analysis.get("cut_boundary_cache_path") or "") == cache_path
                            and not list(analysis.get("cut_boundaries", []) or [])
                        ):
                            for key in (
                                "cut_boundary_prescan_done",
                                "cut_boundary_cache_path",
                                "cut_boundary_cache_type",
                            ):
                                analysis.pop(key, None)
                            write_project_file(project_path, project)
                    except Exception as inner_exc:
                        get_logger().log(f"  ⚠️ [컷 경계] 빈 캐시 상태 정리 실패: {inner_exc}")
                return None

            # ✅ 핵심: 현재 프로젝트 파일은 그대로 두고 analysis.cut_boundaries만 주입
            if project_path and os.path.exists(project_path):
                project = read_project_file(project_path)

                project.setdefault("analysis", {})
                project["analysis"]["cut_boundaries"] = list(rows)
                project["analysis"]["cut_boundary_provisional_boundaries"] = []
                project["analysis"]["cut_boundary_prescan_done"] = True
                project["analysis"]["cut_boundary_cache_path"] = cache_path
                project["analysis"]["cut_boundary_cache_type"] = "cut_boundaries_only"
                project["analysis"]["cut_boundary_api_version"] = CUT_BOUNDARY_API_VERSION
                project["analysis"]["cut_boundary_algorithm_version"] = CUT_BOUNDARY_ALGORITHM_VERSION
                project["analysis"]["cut_boundary_algorithm_id"] = CUT_BOUNDARY_ALGORITHM_ID

                sync_project_cut_boundaries(project, settings=settings, provisional_boundaries=[])

                write_project_file(project_path, project)
                self._clear_completed_cut_boundary_provisionals(
                    project_path,
                    settings=settings,
                    detected=rows,
                    emit=True,
                )
                try:
                    self._force_cut_boundary_topicless_segments_to_project(
                        project_path,
                        rows,
                        files=list(files or []),
                        done=True,
                    )
                except Exception as topicless_exc:
                    get_logger().log(
                        f"  ⚠️ [컷 경계] 캐시 재사용 중분류 세그먼트 확정 실패: {topicless_exc}"
                    )

            get_logger().log(
                f"  ♻️ [컷 경계] 캐시 재사용: {len(rows)}개 "
                f"(analysis.cut_boundaries only, {cache_path})"
            )
            try:
                self._cut_boundary_prescan_completed = True
            except Exception:
                pass
            emitter = getattr(self, "_ui_emit", None)
            if callable(emitter):
                try:
                    emitter(
                        "_sig_update_project_boundary_times",
                        [dict(row) for row in list(rows or []) if isinstance(row, dict)],
                    )
                except Exception:
                    pass
                emitter("_sig_refresh_cut_boundary_placeholder")
            counter = getattr(self, "_emit_cut_boundary_count_to_sidebar", None)
            if callable(counter):
                try:
                    counter(len(rows), done=True)
                except Exception:
                    pass
            return rows
        except Exception as exc:
            get_logger().log(f"  ⚠️ [컷 경계] 캐시 불러오기 실패: {exc}")
            return None

    def _save_cut_boundary_cache_for_start(self, files: list[str], settings: dict, rows: list[dict]) -> None:
        """Save only cut-boundary analysis data for future reuse.

        IMPORTANT:
        - Do NOT move/copy the actual project file into cache.
        - The project file remains the source of truth for the current work.
        - Cache stores only analysis.cut_boundaries-compatible rows.
        """
        try:
            if not list(rows or []):
                get_logger().log("  💾 [컷 경계] 빈 결과 캐시 저장 생략: 다음 열기에서 백그라운드 재확인")
                return

            import time
            cache_path = self._cut_boundary_cache_path_for_start(files, settings)

            payload = {
                "version": 7,
                "cut_boundary_api_version": CUT_BOUNDARY_API_VERSION,
                "cut_boundary_algorithm_version": CUT_BOUNDARY_ALGORITHM_VERSION,
                "cut_boundary_algorithm_id": CUT_BOUNDARY_ALGORITHM_ID,
                "created_at": time.time(),
                "cache_type": "cut_boundaries_only",
                "files": [],
                "settings": self._cut_boundary_cache_settings_payload(settings),
                # ✅ 핵심: 프로젝트 전체가 아니라 컷 경계 데이터만 저장
                "analysis": {
                    "cut_boundaries": list(rows or []),
                },
            }

            for p in list(files or []):
                try:
                    st = os.stat(p)
                    payload["files"].append({
                        "path": os.path.abspath(str(p)),
                        "size": int(st.st_size),
                        "mtime_ns": int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))),
                        "fingerprint_digest": media_fingerprint_digest(p, sample_bytes=256 * 1024, include_samples=True),
                    })
                except Exception:
                    payload["files"].append({
                        "path": os.path.abspath(str(p)),
                        "size": 0,
                        "mtime_ns": 0,
                        "fingerprint_digest": "",
                    })

            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

            get_logger().log(
                f"  💾 [컷 경계] 캐시 저장 완료: {len(rows or [])}개 "
                f"(analysis.cut_boundaries only, {cache_path})"
            )
        except Exception as exc:
            get_logger().log(f"  ⚠️ [컷 경계] 캐시 저장 실패: {exc}")

    def _wait_cut_boundary_prescan_before_stt(self):
        """Block backend pipeline thread until cut-boundary prescan is done.

        This does not block the Qt UI thread. It only prevents STT1/STT2 from
        starting before the absolute cut-boundary middle segments are ready.
        """
        try:
            thread = getattr(self, "_cut_boundary_prescan_thread", None)
            if thread is not None and thread.is_alive():
                get_logger().log("  🎬 [컷 경계] STT 시작 전 자동 분석 완료 대기 중...")
                thread.join()
                get_logger().log("  ✅ [컷 경계] STT 시작 전 자동 분석 완료")
                try:
                    self._ui_emit("_sig_refresh_cut_boundary_placeholder")
                except Exception:
                    pass
            try:
                settings = load_settings()
            except Exception:
                settings = {}
            wait_follower = bool(settings.get("cut_boundary_wait_follower_before_stt", True))
            follower = getattr(self, "_cut_boundary_follower_thread", None)
            if (
                wait_follower
                and follower is not None
                and follower.is_alive()
                and follower is not threading.current_thread()
            ):
                get_logger().log("  🎬 [컷 경계] STT 시작 전 후발대 rollback 검증 완료 대기 중...")
                follower.join()
                get_logger().log("  ✅ [컷 경계] 후발대 rollback 검증 완료 후 STT hard cut 확정")
                try:
                    self._ui_emit("_sig_refresh_cut_boundary_placeholder")
                except Exception:
                    pass
        except Exception as exc:
            get_logger().log(f"  ⚠️ [컷 경계] STT 시작 전 대기 실패: {exc}")


    def _cut_boundary_sec_from_row(self, row) -> float | None:
        try:
            if isinstance(row, dict):
                return float(row.get("timeline_sec", row.get("time", row.get("start", 0.0))) or 0.0)
            return float(row)
        except Exception:
            return None

    def _cut_boundary_candidate_key(self, row) -> str:
        sec = self._cut_boundary_sec_from_row(row)
        if sec is None:
            sec = 0.0
        try:
            clip_idx = int(row.get("clip_idx", 0) or 0) if isinstance(row, dict) else 0
        except Exception:
            clip_idx = 0
        return f"{clip_idx}:{float(sec):.3f}"

    _fast_cut_boundary_prescan_settings = staticmethod(fast_cut_boundary_prescan_settings)
    _cut_boundary_adaptive_prescan_plan = staticmethod(cut_boundary_adaptive_prescan_plan)

    def _mark_cut_boundary_rows_following(self, provisional_rows: list[dict], rows: list[dict]) -> bool:
        """Mark pioneer candidates as actively checked by the follower worker."""
        candidate_keys = {
            self._cut_boundary_candidate_key(row)
            for row in list(rows or [])
            if isinstance(row, dict)
        }
        if not candidate_keys:
            return False
        changed = False
        for idx, item in enumerate(list(provisional_rows or [])):
            if not isinstance(item, dict):
                continue
            key = str(item.get("candidate_key") or self._cut_boundary_candidate_key(item))
            if key not in candidate_keys:
                continue
            marked = dict(item)
            marked["candidate_key"] = key
            marked["status"] = "verifying"
            marked["detector_stage"] = "follower"
            marked["follower_active"] = True
            marked["line_color"] = "#FFCC00"
            marked["line_style"] = "dash"
            marked["ui_label"] = "후발대 확인"
            provisional_rows[idx] = marked
            changed = True
        return changed

    def _remove_cut_boundary_checked_rows(self, provisional_rows: list[dict], rows: list[dict]) -> bool:
        """Remove follower-checked temporary candidates from the UI list.

        Relocated rollback hints are intentionally kept because they are new
        provisional evidence for a later verification pass.
        """
        candidate_keys = {
            self._cut_boundary_candidate_key(row)
            for row in list(rows or [])
            if isinstance(row, dict)
        }
        if not candidate_keys:
            return False
        kept: list[dict] = []
        changed = False
        for item in list(provisional_rows or []):
            if not isinstance(item, dict):
                kept.append(item)
                continue
            if bool(item.get("follower_relocated") or item.get("rollback_relocated")):
                kept.append(item)
                continue
            key = str(item.get("candidate_key") or self._cut_boundary_candidate_key(item))
            if key in candidate_keys:
                changed = True
                continue
            kept.append(item)
        if changed:
            provisional_rows[:] = kept
        return changed

    def _cut_boundary_placeholder_duration(self, files=None) -> float:
        try:
            if hasattr(self, "_cut_boundary_total_duration_for_start"):
                return float(self._cut_boundary_total_duration_for_start(list(files or [])) or 0.0)
        except Exception:
            pass
        try:
            clip_boundaries = list(getattr(self.ui, "_multiclip_boundaries", []) or [])
            if clip_boundaries:
                return max(float(x.get("end", 0.0) or 0.0) for x in clip_boundaries)
        except Exception:
            pass
        try:
            vp = getattr(self, "video_processor", None)
            if vp is not None and files:
                return float(vp._media_duration_for_progress(list(files or [])[0]) or 0.0)
        except Exception:
            pass
        return 0.0

    def _reviewed_cut_boundary_rows_for_middle_segments(
        self,
        provisional_rows,
        *,
        detected_rows=None,
    ) -> list[dict]:
        try:
            from core.cut_boundary import normalize_cut_boundaries
        except Exception:
            normalize_cut_boundaries = None

        merged = reviewed_middle_source_rows(
            provisional_rows,
            detected_rows=detected_rows,
            candidate_key_resolver=getattr(self, "_cut_boundary_candidate_key", None),
        )
        if callable(normalize_cut_boundaries):
            try:
                merged = normalize_cut_boundaries(list(merged))
            except Exception:
                pass
        return merged

    def _build_cut_boundary_topicless_rows(
        self,
        detected,
        *,
        files=None,
        done: bool = False,
        prefer_all_frames: bool = False,
    ) -> list[dict]:
        media_duration = self._cut_boundary_placeholder_duration(files)
        cut_rows = []
        for row in list(detected or []):
            sec = self._cut_boundary_sec_from_row(row)
            if sec is None or sec <= 0.0:
                continue
            cut_rows.append(dict(row) if isinstance(row, dict) else {"timeline_sec": round(float(sec), 3), "time": round(float(sec), 3)})
        return build_middle_segments_for_stage(
            cut_rows,
            media_duration=media_duration,
            files=list(files or []),
            done=bool(done),
            prefer_all_boundary_frames=bool(prefer_all_frames),
        )

    def _placeholder_rows_can_be_overwritten(self, rows) -> bool:
        rows = list(rows or [])
        if not rows:
            return True

        for row in rows:
            if not isinstance(row, dict):
                return False

            title = str(row.get("title", row.get("name", "")) or "")
            tags = row.get("tags", []) or []
            if isinstance(tags, str):
                tags = [tags]

            if (
                row.get("is_topicless_placeholder")
                or row.get("is_cut_boundary_placeholder")
                or row.get("source") == "cut_boundary"
                or title == "주제없음"
                or "컷경계" in tags
            ):
                continue

            # 이미 LLM이 만든 실제 중분류가 있으면 자동 placeholder가 덮어쓰면 안 됨
            return False

        return True

    def _force_cut_boundary_topicless_segments_to_project(
        self,
        project_path: str,
        detected,
        *,
        files=None,
        done: bool = False,
        middle_source_rows=None,
        prefer_all_frames: bool = False,
    ) -> list[dict]:
        """Persist gray topicless middle segments immediately.

        This fixes the case where cut boundaries are detected but the gray
        middle segment does not appear because only analysis.cut_boundaries
        was saved.
        """
        try:
            if not project_path or not os.path.exists(project_path):
                return []

            rows = self._build_cut_boundary_topicless_rows(
                detected if middle_source_rows is None else middle_source_rows,
                files=list(files or []),
                done=bool(done),
                prefer_all_frames=bool(prefer_all_frames),
            )
            if not rows:
                return []

            project = read_project_file(project_path)
            from core.roughcut.cut_boundary_placeholder import store_topicless_placeholders_in_project_data

            store_topicless_placeholders_in_project_data(
                project,
                rows,
                cut_boundaries=detected,
                finalized=bool(done),
            )

            write_project_file(project_path, project)

            if bool(done):
                get_logger().log(
                    f"  ▒ [컷 경계] 주제없음 중분류 세그먼트 확정 ({len(rows)}개)"
                )

            # UI 새로고침 신호를 넓게 호출
            for sig in (
                "_sig_refresh_cut_boundary_placeholder",
                "_sig_refresh_roughcut",
                "_sig_reload_roughcut",
                "_sig_refresh_timeline",
                "_sig_redraw_timeline",
            ):
                try:
                    self._ui_emit(sig)
                except Exception:
                    pass

            return rows
        except Exception as exc:
            try:
                get_logger().log(f"  ⚠️ [컷 경계] 주제없음 회색 중분류 저장 실패: {exc}")
            except Exception:
                pass
            return []

    def _emit_cut_boundary_count_to_sidebar(self, count: int, *, percent=None, done: bool = False):
        """Update left queue/sidebar status with throttling.

        Avoid logging/emitting the same status repeatedly from scan progress.
        """
        try:
            count = int(count or 0)
        except Exception:
            count = 0

        if done:
            status = f"✅ {count} 컷 경계 완료"
            state_key = ("done", count)
        elif count > 0:
            status = f"{count} 컷 경계"
            state_key = ("count", count)
        else:
            if percent is None:
                status = "컷 경계 확인 중"
                state_key = ("progress", None)
            else:
                pct = max(0, min(100, int(percent or 0)))
                # 5% 단위로만 갱신해서 0% 로그가 수십 번 찍히는 문제 방지
                pct_bucket = (pct // 5) * 5
                status = f"컷 경계 확인 중 {pct_bucket}%"
                state_key = ("progress", pct_bucket)

        last_key = getattr(self, "_cut_boundary_sidebar_last_key", None)
        if last_key == state_key:
            return

        self._cut_boundary_sidebar_last_key = state_key

        candidates = []
        try:
            cur = getattr(self.ui, "_current_file_idx", None)
            if cur is not None:
                candidates.append(max(0, int(cur) - 1))
        except Exception:
            pass

        try:
            qi = getattr(self, "_queue_index", None)
            if qi is not None:
                candidates.append(max(0, int(qi)))
        except Exception:
            pass

        if not candidates:
            candidates.append(0)

        seen = set()
        for qi in candidates:
            if qi in seen:
                continue
            seen.add(qi)
            try:
                self._ui_emit("_sig_update_queue", int(qi), status, "", "", "")
            except Exception:
                pass

        return


    def _auto_scan_cut_boundaries_for_start(self, project_path: str, files: list[str]) -> list[dict]:
        """Start cut-boundary prescan without blocking the Qt/UI thread.

        The old implementation ran detect_media_cut_boundaries() synchronously.
        That made the app show a busy cursor and prevented other buttons from
        being selected while the scan was running.
        """
        try:
            import threading

            old_thread = getattr(self, "_cut_boundary_prescan_thread", None)
            if old_thread is not None and old_thread.is_alive():
                force_rescan_requested = bool(getattr(self, "_force_cut_boundary_rescan_once", False))
                if force_rescan_requested:
                    try:
                        self._cut_boundary_prescan_pending_request = {
                            "project_path": str(project_path or ""),
                            "files": list(files or []),
                            "force_rescan": True,
                        }
                    except Exception:
                        pass
                self._ui_emit("_sig_set_cut_boundary_scan_active", True)
                try:
                    self._emit_cut_boundary_count_to_sidebar(0, percent=0, done=False)
                except Exception:
                    pass
                if force_rescan_requested:
                    try:
                        get_logger().log(
                            "  🔄 [컷 경계] 진행 중 스캔이 끝나면 음성/임시/후발대 재확인을 바로 다시 시작하도록 예약했습니다"
                        )
                    except Exception:
                        pass
                return []

            def _worker():
                pending_request = None
                try:
                    self._auto_scan_cut_boundaries_for_start_sync(project_path, list(files or []))
                except Exception as exc:
                    try:
                        get_logger().log(f"  ⚠️ [컷 경계] 백그라운드 자동 분석 실패: {exc}")
                    except Exception:
                        pass
                finally:
                    try:
                        if getattr(self, "_cut_boundary_prescan_thread", None) is threading.current_thread():
                            self._cut_boundary_prescan_thread = None
                    except Exception:
                        pass
                    try:
                        raw_pending = getattr(self, "_cut_boundary_prescan_pending_request", None)
                        if isinstance(raw_pending, dict) and raw_pending:
                            pending_request = dict(raw_pending)
                            self._cut_boundary_prescan_pending_request = None
                    except Exception:
                        pending_request = None
                    if pending_request:
                        try:
                            next_project_path = str(pending_request.get("project_path") or project_path or "")
                            next_files = list(pending_request.get("files") or list(files or []))
                            if bool(pending_request.get("force_rescan", False)):
                                self._force_cut_boundary_rescan_once = True
                                self._cut_boundary_prescan_completed = False
                            get_logger().log("  🔄 [컷 경계] 대기 중이던 재확인 요청을 이어서 시작합니다")
                            self._auto_scan_cut_boundaries_for_start(next_project_path, next_files)
                        except Exception as rerun_exc:
                            try:
                                get_logger().log(
                                    f"  ⚠️ [컷 경계] 대기 중 재확인 재시작 실패: {rerun_exc}"
                                )
                            except Exception:
                                pass

            thread = threading.Thread(
                target=_worker,
                name="cut-boundary-prescan-worker",
                daemon=True,
            )
            self._cut_boundary_prescan_thread = thread
            self._ui_emit("_sig_set_cut_boundary_scan_active", True)
            try:
                self._emit_cut_boundary_count_to_sidebar(0, percent=0, done=False)
            except Exception:
                pass
            thread.start()
            get_logger().log("  🎬 [컷 경계] 백그라운드 자동 분석 시작")
            return []
        except Exception as exc:
            self._ui_emit("_sig_set_cut_boundary_scan_active", False)
            get_logger().log(f"  ⚠️ [컷 경계] 백그라운드 자동 분석 시작 실패: {exc}")
            return []

    def _auto_scan_cut_boundaries_for_start_sync(self, project_path: str, files: list[str]) -> list[dict]:
        """Populate project cut boundaries before STT starts when the feature is enabled."""
        try:
            from core.cut_boundary import (
                cut_boundary_enabled,
                normalize_cut_boundaries,
                scan_media_cut_boundary_provisionals,
                sync_project_cut_boundaries,
                cut_boundary_scan_profile,
                verify_media_cut_boundary_rows,
            )

            settings = dict(apply_autopilot_runtime_policy(load_settings()) or {})
            try:
                duration_sec = float(self._cut_boundary_placeholder_duration(files) or 0.0)
                if duration_sec > 0.0:
                    settings["cut_boundary_media_duration_sec"] = duration_sec
            except Exception:
                pass
            try:
                scan_profile = cut_boundary_scan_profile(settings)
            except Exception:
                scan_profile = {"level": "medium", "label": "중간 - 9개 중 꽉찬 십자가 5개", "mask": "x5", "positions": (0, 2, 4, 6, 8)}
            settings["scan_cut_boundary_resolved_level"] = str(scan_profile.get("resolved_level") or scan_profile.get("level") or "medium")
            settings["scan_cut_boundary_resolved_mask"] = str(scan_profile.get("mask") or "")
            if bool(scan_profile.get("adaptive", False)):
                try:
                    get_logger().log(
                        f"  🎬 [컷 경계] 자동 레벨 적용: {settings['scan_cut_boundary_resolved_level']} "
                        f"({float(settings.get('cut_boundary_media_duration_sec', 0.0) or 0.0):.1f}s)"
                    )
                except Exception:
                    pass
            if not cut_boundary_enabled(settings):
                get_logger().log("  🎬 [컷 경계] 비활성화되어 있어 분석을 건너뜁니다")
                return []
            if not project_path or not os.path.exists(project_path):
                get_logger().log("  ⚠️ [컷 경계] 프로젝트 경로가 없어 분석을 건너뜁니다")
                return []

            settings = self._fast_cut_boundary_prescan_settings(settings)
            adaptive_plan = self._cut_boundary_adaptive_prescan_plan(settings, files)
            settings["scan_cut_follower_stream_start_percent"] = int(adaptive_plan["stream_start_percent"])
            settings["scan_cut_follower_stream_batch_size"] = int(adaptive_plan["stream_batch_size"])
            settings["scan_cut_follower_stream_min_interval_sec"] = float(adaptive_plan["stream_min_interval_sec"])
            settings["scan_cut_follower_deferred_until_pioneer_done"] = bool(
                adaptive_plan.get("follower_start_after_pioneer", False)
            )
            settings["scan_cut_provisional_sample_step_sec"] = float(
                adaptive_plan.get(
                    "provisional_sample_step_sec",
                    settings.get("scan_cut_auto_sample_step_sec", 2.0),
                )
                or 2.0
            )
            settings["scan_cut_pioneer_sequential_decode_enabled"] = bool(
                adaptive_plan.get("pioneer_sequential_decode", False)
            )
            realtime_preview_enabled = _truthy_setting(settings.get("scan_cut_realtime_preview_enabled"), True)
            provisional_settings, provisional_scan_profile = build_provisional_native_settings(
                settings,
                sample_step_sec=float(settings.get("scan_cut_provisional_sample_step_sec", 1.0) or 1.0),
            )
            follower_verify_settings_template, follower_scan_profile = build_follower_native_verify_settings(settings)
            provisional_settings["scan_cut_boundary_resolved_level"] = str(
                provisional_scan_profile.get("resolved_level")
                or provisional_scan_profile.get("level")
                or "low"
            )
            provisional_settings["scan_cut_boundary_resolved_mask"] = str(
                provisional_scan_profile.get("mask") or ""
            )
            settings["scan_cut_boundary_provisional_level"] = "low"
            settings["scan_cut_boundary_provisional_mask"] = str(provisional_scan_profile.get("mask") or "")
            try:
                get_logger().log(
                    "  🎬 [컷 경계] 선발대는 720p 3×3 십자가 4칸으로 임시선을 만들고, "
                    "후발대는 1080p 5×5 중앙 3×3 롤백 검증으로 확정합니다"
                )
                if adaptive_plan.get("follower_start_after_pioneer"):
                    get_logger().log(
                        "  🚀 [컷 경계] adaptive: 긴 4K도 동일 규칙 유지, "
                        "후발대는 선발대 완료 후 지연 검증"
                    )
                else:
                    get_logger().log(
                        "  🚀 [컷 경계] 임시선 고속 경로: "
                        "OpenCV 4-way 선발대 + native 후발대 병렬 롤백 검증"
                    )
            except Exception:
                pass

            try:
                initial_rows = self._force_cut_boundary_topicless_segments_to_project(
                    project_path,
                    [],
                    files=list(files or []),
                    done=False,
                )
                if initial_rows and realtime_preview_enabled:
                    self._ui_emit("_sig_preview_cut_boundary_topicless_segments", list(initial_rows))
            except Exception as initial_exc:
                get_logger().log(f"  ⚠️ [컷 경계] 초기 A 중분류 생성 실패: {initial_exc}")

            cached = self._load_cut_boundary_cache_for_start(project_path, files, settings)
            if cached is not None:
                return cached

            clip_boundaries = list(getattr(self.ui, "_multiclip_boundaries", []) or [])
            detected: list[dict] = []
            provisional_rows: list[dict] = []
            reviewed_middle_rows: list[dict] = []
            list_lock = threading.RLock()
            follower_queue: "queue.Queue[dict | None]" = queue.Queue()
            self._cut_boundary_provisional_rows = []
            total_files = len(list(files or []))
            progress_preview_interval_sec = 0.18
            last_preview_emit_mono = 0.0
            last_detected_save_mono = 0.0
            pioneer_done_by_clip: dict[int, bool] = {}
            pioneer_progress_by_clip: dict[int, dict[int, int]] = {}
            last_logged_progress_pct_by_clip: dict[int, int] = {}
            clip_path_by_idx = {idx: path for idx, path in enumerate(list(files or []))}
            clip_offset_by_idx: dict[int, float] = {}
            follower_enqueued_keys: set[str] = set()
            follower_pending_by_clip: dict[int, list[dict]] = {}
            follower_last_enqueue_mono_by_clip: dict[int, float] = {}
            follower_stream_logged_by_clip: set[int] = set()
            follower_start_after_pioneer = bool(adaptive_plan.get("follower_start_after_pioneer", False))
            follower_progress_lock = threading.Lock()
            follower_total_candidates = 0
            follower_checked_candidates = 0
            follower_verified_candidates = 0
            try:
                follower_start_delay_sec = float(adaptive_plan.get("follower_start_delay_sec", 0.0) or 0.0)
            except Exception:
                follower_start_delay_sec = 0.0
            try:
                follower_stream_start_pct = max(
                    0,
                    min(100, int(settings.get("scan_cut_follower_stream_start_percent", 25) or 25)),
                )
            except Exception:
                follower_stream_start_pct = 25
            try:
                follower_stream_batch_size = max(
                    4,
                    int(settings.get("scan_cut_follower_stream_batch_size", 16) or 16),
                )
            except Exception:
                follower_stream_batch_size = 16
            try:
                follower_stream_min_interval_sec = max(
                    0.0,
                    float(settings.get("scan_cut_follower_stream_min_interval_sec", 0.75) or 0.75),
                )
            except Exception:
                follower_stream_min_interval_sec = 0.75
            try:
                follower_micro_batch_size = max(
                    4,
                    int(
                        settings.get(
                            "scan_cut_follower_verify_micro_batch_size",
                            follower_stream_batch_size,
                        )
                        or follower_stream_batch_size
                    ),
                )
            except Exception:
                follower_micro_batch_size = max(4, int(follower_stream_batch_size or 16))
            try:
                follower_micro_batch_cap = max(
                    4,
                    int(settings.get("scan_cut_follower_verify_micro_batch_max", 16) or 16),
                )
            except Exception:
                follower_micro_batch_cap = 16
            if follower_start_after_pioneer:
                # 긴 4K 지연 후발대는 한 배치가 너무 커지면 verify_media_cut_boundary_rows()
                # 내부에서 오래 머물러 UI/로그가 멈춘 것처럼 보인다. 벤치마크 기준 4-way
                # 검증은 유지하되 작은 배치로 끊어 실시간 진행과 취소 반응성을 살린다.
                follower_micro_batch_size = max(
                    4,
                    min(
                        int(follower_micro_batch_size or 16),
                        int(follower_stream_batch_size or 16),
                        int(follower_micro_batch_cap or 16),
                    ),
                )
            step_sec = max(
                0.25,
                float(
                    settings.get(
                        "scan_cut_auto_sample_step_sec",
                        scan_profile.get("sample_step_sec", 2.0),
                    )
                    or scan_profile.get("sample_step_sec", 2.0)
                    or 1.0
                ),
            )
            provisional_step_sec = max(
                0.25,
                float(settings.get("scan_cut_provisional_sample_step_sec", step_sec) or step_sec),
            )
            if realtime_preview_enabled:
                self._ui_emit("_sig_set_cut_boundary_scan_active", True)
            try:
                self._emit_cut_boundary_count_to_sidebar(0, percent=0, done=False)
            except Exception:
                pass

            def _style_provisional_row(row: dict) -> dict:
                styled = provisional_boundary_row(row)
                styled["verified"] = False
                styled.setdefault("candidate_key", self._cut_boundary_candidate_key(styled))
                if is_audio_gain_boundary(styled):
                    decision = hybrid_cut_boundary_decision(styled, settings)
                    styled["autopilot_cut_boundary_decision"] = decision
                    styled["provisional_type"] = "audio_gain"
                    styled.setdefault("source", "audio_gain_provisional")
                else:
                    styled["autopilot_cut_boundary_decision"] = hybrid_cut_boundary_decision(styled, settings)
                    styled.setdefault("source", "visual_provisional")
                return styled

            def _checked_provisional_row(row: dict, *, verified: bool = False) -> dict:
                checked = checked_provisional_boundary_row(row, verified=verified)
                checked.setdefault("candidate_key", self._cut_boundary_candidate_key(checked))
                checked["ui_label"] = ""
                return checked

            def _merge_reviewed_middle_rows(rows_to_merge: list[dict]) -> bool:
                nonlocal reviewed_middle_rows
                incoming = [dict(row) for row in list(rows_to_merge or []) if isinstance(row, dict)]
                if not incoming:
                    return False
                merged = [dict(row) for row in list(reviewed_middle_rows or []) if isinstance(row, dict)]
                key_to_index: dict[str, int] = {}
                for idx, item in enumerate(list(merged)):
                    key = str(item.get("candidate_key") or self._cut_boundary_candidate_key(item))
                    item["candidate_key"] = key
                    key_to_index[key] = idx
                changed = False
                for item in incoming:
                    key = str(item.get("candidate_key") or self._cut_boundary_candidate_key(item))
                    item["candidate_key"] = key
                    prev_idx = key_to_index.get(key)
                    if prev_idx is None:
                        key_to_index[key] = len(merged)
                        merged.append(item)
                        changed = True
                        continue
                    if merged[prev_idx] != item:
                        merged[prev_idx] = item
                        changed = True
                if not changed:
                    return False
                reviewed_middle_rows = self._reviewed_cut_boundary_rows_for_middle_segments(
                    merged,
                    detected_rows=[],
                )
                return True

            def _save_detected_now(*, force: bool = False):
                nonlocal last_detected_save_mono
                if not bool(settings.get("scan_cut_incremental_project_save_enabled", False)):
                    return False
                if not force:
                    try:
                        interval_sec = max(
                            0.0,
                            float(settings.get("scan_cut_incremental_save_interval_sec", 0.75) or 0.0),
                        )
                    except Exception:
                        interval_sec = 0.75
                    now_mono = time.monotonic()
                    if interval_sec > 0.0 and (now_mono - last_detected_save_mono) < interval_sec:
                        return False
                try:
                    with list_lock:
                        detected_snapshot = [dict(item) for item in list(detected)]
                        provisional_snapshot = [dict(item) for item in list(provisional_rows)]
                    project = read_project_file(project_path)
                    project.setdefault("analysis", {})
                    project["analysis"]["cut_boundaries"] = detected_snapshot
                    project["analysis"]["cut_boundary_provisional_boundaries"] = provisional_snapshot
                    sync_project_cut_boundaries(
                        project,
                        settings=settings,
                        provisional_boundaries=provisional_snapshot,
                    )
                    write_project_file(project_path, project)
                    try:
                        self._cut_boundary_pipeline_cache = None
                    except Exception:
                        pass
                    last_detected_save_mono = time.monotonic()
                    return True
                except Exception as exc:
                    get_logger().log(f"  ⚠️ [컷 경계] 중간 저장 실패: {exc}")
                    return False

            def _progress(info: dict):
                nonlocal last_preview_emit_mono
                try:
                    clip_no = int(info.get("clip_idx", 0) or 0) + 1
                except Exception:
                    clip_no = 1
                pct = int(info.get("percent", 0) or 0)
                ts = float(info.get("timestamp", 0.0) or 0.0)
                dur = float(info.get("duration", 0.0) or 0.0)
                found = int(info.get("provisional_detected", info.get("detected", 0)) or 0)
                try:
                    worker_idx = int(info.get("worker_idx", 0) or 0)
                except Exception:
                    worker_idx = 0
                try:
                    raw_worker_total = info.get("worker_total")
                    worker_total = int(raw_worker_total) if raw_worker_total is not None else 0
                except Exception:
                    worker_total = 0
                try:
                    worker_pct = int(info.get("worker_percent", pct) or pct)
                except Exception:
                    worker_pct = pct
                clip_progress = pioneer_progress_by_clip.setdefault(clip_no, {})
                clip_progress[worker_idx] = max(0, min(100, worker_pct))
                if worker_total <= 0:
                    worker_total = max(1, len(clip_progress))
                aggregate_pct = max(
                    0,
                    min(100, int(round(sum(clip_progress.values()) / float(max(1, worker_total))))),
                )
                try:
                    self._emit_cut_boundary_count_to_sidebar(found, percent=aggregate_pct, done=False)
                except Exception:
                    pass
                now_mono = time.monotonic()
                next_ts = min(dur, ts + provisional_step_sec) if dur > 0.0 else (ts + provisional_step_sec)
                clip_offset = 0.0
                if (clip_no - 1) < len(clip_boundaries):
                    try:
                        clip_offset = float(clip_boundaries[clip_no - 1].get("start", 0.0) or 0.0)
                    except Exception:
                        clip_offset = 0.0
                if realtime_preview_enabled and (
                    (now_mono - last_preview_emit_mono) >= progress_preview_interval_sec or pct >= 100
                ):
                    last_preview_emit_mono = now_mono
                    self._ui_emit("_sig_preview_cut_boundary_scan", clip_offset + ts, clip_offset + next_ts)
                last_logged_pct = int(last_logged_progress_pct_by_clip.get(clip_no, -1))
                if aggregate_pct > last_logged_pct:
                    last_logged_progress_pct_by_clip[clip_no] = aggregate_pct
                    try:
                        get_logger().log(
                            f"  🎬 [선발대 진행] 파일 {clip_no}/{total_files} {aggregate_pct}% "
                            f"(임시 {found}개)"
                        )
                    except Exception:
                        pass
                _maybe_flush_streaming_follower(clip_no - 1, aggregate_pct=aggregate_pct)

            def _follower_progress_pct(clip_idx: int) -> int:
                clip_progress = pioneer_progress_by_clip.get(int(clip_idx) + 1, {})
                if not clip_progress:
                    return 0
                return int(round(sum(clip_progress.values()) / float(max(1, len(clip_progress)))))

            def _follower_job_batch_size(reason: str, row_count: int) -> int:
                if row_count <= 0:
                    return max(1, follower_micro_batch_size)
                if str(reason or "") == "stream":
                    return max(1, min(row_count, follower_stream_batch_size))
                if follower_start_after_pioneer:
                    return max(1, min(row_count, follower_micro_batch_size))
                return max(1, min(row_count, follower_stream_batch_size))

            def _follower_verify_settings(reason: str, row_count: int) -> dict:
                _ = (reason, row_count)
                return dict(follower_verify_settings_template)

            def _compact_follower_rows_for_verify(rows: list[dict], reason: str) -> tuple[list[dict], list[dict]]:
                if not rows or str(reason or "") == "stream":
                    return rows, []
                if not follower_start_after_pioneer:
                    return rows, []
                if not bool(settings.get("scan_cut_follower_candidate_compact_enabled", True)):
                    return rows, []
                try:
                    audio_gap_sec = max(
                        0.0,
                        float(settings.get("scan_cut_follower_audio_candidate_compact_gap_sec", 2.25) or 2.25),
                    )
                except Exception:
                    audio_gap_sec = 2.25
                try:
                    visual_gap_sec = max(
                        0.0,
                        float(settings.get("scan_cut_follower_visual_candidate_compact_gap_sec", 0.75) or 0.75),
                    )
                except Exception:
                    visual_gap_sec = 0.75
                if audio_gap_sec <= 0.0 and visual_gap_sec <= 0.0:
                    return rows, []

                def _row_sec(row: dict) -> float:
                    try:
                        return float(row.get("clip_local_sec", row.get("timeline_sec", row.get("time", 0.0))) or 0.0)
                    except Exception:
                        return 0.0

                def _row_clip(row: dict) -> int:
                    try:
                        return int(row.get("clip_idx", 0) or 0)
                    except Exception:
                        return 0

                def _rank(row: dict) -> tuple[float, float, float, float]:
                    audio = is_audio_gain_boundary(row)
                    try:
                        gain = abs(float(row.get("audio_gain_db_delta", 0.0) or 0.0))
                    except Exception:
                        gain = 0.0
                    try:
                        score = float(row.get("score", 0.0) or 0.0)
                    except Exception:
                        score = 0.0
                    try:
                        regions = float(row.get("regions", 0.0) or 0.0)
                    except Exception:
                        regions = 0.0
                    return (0.0 if audio else 1.0, gain, score, regions)

                sorted_rows = sorted(
                    [dict(row) for row in list(rows or []) if isinstance(row, dict)],
                    key=lambda row: (_row_clip(row), _row_sec(row)),
                )
                kept: list[dict] = []
                dropped: list[dict] = []
                cluster: list[dict] = []

                def _flush_cluster():
                    if not cluster:
                        return
                    best = max(cluster, key=_rank)
                    kept.append(best)
                    best_key = str(best.get("candidate_key") or self._cut_boundary_candidate_key(best))
                    for item in cluster:
                        item_key = str(item.get("candidate_key") or self._cut_boundary_candidate_key(item))
                        if item_key != best_key:
                            dropped.append(item)

                for row in sorted_rows:
                    if not cluster:
                        cluster = [row]
                        continue
                    same_clip = _row_clip(row) == _row_clip(cluster[-1])
                    audio_cluster = is_audio_gain_boundary(row) and all(is_audio_gain_boundary(item) for item in cluster)
                    gap = audio_gap_sec if audio_cluster else visual_gap_sec
                    if same_clip and gap > 0.0 and (_row_sec(row) - _row_sec(cluster[-1])) <= gap:
                        cluster.append(row)
                        continue
                    _flush_cluster()
                    cluster = [row]
                _flush_cluster()
                if not dropped:
                    return rows, []
                return kept, dropped

            def _queue_follower_rows(clip_idx: int, rows: list[dict], *, reason: str) -> int:
                nonlocal follower_total_candidates
                queued: list[dict] = []
                with list_lock:
                    for row in list(rows or []):
                        if not isinstance(row, dict):
                            continue
                        key = str(row.get("candidate_key") or self._cut_boundary_candidate_key(row))
                        if key in follower_enqueued_keys:
                            continue
                        follower_enqueued_keys.add(key)
                        item = dict(row)
                        item["candidate_key"] = key
                        queued.append(item)
                if not queued:
                    return 0
                queued, compacted_rows = _compact_follower_rows_for_verify(queued, reason)
                if compacted_rows:
                    compacted_keys = {
                        str(row.get("candidate_key") or self._cut_boundary_candidate_key(row))
                        for row in compacted_rows
                    }
                    with list_lock:
                        provisional_rows[:] = [
                            item
                            for item in provisional_rows
                            if str(item.get("candidate_key") or self._cut_boundary_candidate_key(item))
                            not in compacted_keys
                        ]
                        self._cut_boundary_provisional_rows = [dict(item) for item in provisional_rows]
                        preview_rows = [dict(item) for item in provisional_rows]
                    if realtime_preview_enabled:
                        self._ui_emit("_sig_preview_cut_boundary_scan_lines", preview_rows)
                    try:
                        get_logger().log(
                            f"  🚀 [컷 경계] 후발대 후보 압축: {len(queued) + len(compacted_rows)}개 → "
                            f"{len(queued)}개 (근접 중복 {len(compacted_rows)}개 생략)"
                        )
                    except Exception:
                        pass
                if not queued:
                    return 0
                with follower_progress_lock:
                    follower_total_candidates += len(queued)
                    total_after_queue = follower_total_candidates
                batch_size = _follower_job_batch_size(str(reason or "stream"), len(queued))
                for batch_start in range(0, len(queued), batch_size):
                    follower_queue.put(
                        {
                            "path": clip_path_by_idx.get(int(clip_idx)),
                            "clip_idx": int(clip_idx),
                            "offset": float(clip_offset_by_idx.get(int(clip_idx), 0.0) or 0.0),
                            "rows": queued[batch_start : batch_start + batch_size],
                            "reason": str(reason or "stream"),
                            "total_after_queue": int(total_after_queue),
                        }
                    )
                if reason == "stream" and int(clip_idx) not in follower_stream_logged_by_clip:
                    follower_stream_logged_by_clip.add(int(clip_idx))
                    try:
                        get_logger().log(
                            f"  🚀 [컷 경계] 파일 {int(clip_idx) + 1}/{total_files} "
                            f"선발대 {follower_stream_start_pct}% 이후 후발대 병렬 검증 시작"
                        )
                    except Exception:
                        pass
                elif reason != "stream" and follower_start_after_pioneer and len(queued) > batch_size:
                    try:
                        get_logger().log(
                            f"  🚀 [컷 경계] 후발대 마이크로 배치: 후보 {len(queued)}개 → "
                            f"{(len(queued) + batch_size - 1) // batch_size}개 작업 "
                            f"(batch={batch_size}, 내부 4-way 검증)"
                        )
                    except Exception:
                        pass
                return len(queued)

            def _maybe_flush_streaming_follower(clip_idx: int, *, aggregate_pct: int | None = None, force: bool = False) -> int:
                if int(clip_idx) not in clip_path_by_idx:
                    return 0
                if follower_start_after_pioneer and not force:
                    return 0
                pct = _follower_progress_pct(int(clip_idx)) if aggregate_pct is None else int(aggregate_pct or 0)
                if not force and pct < follower_stream_start_pct:
                    return 0
                pending = follower_pending_by_clip.get(int(clip_idx), [])
                if not pending:
                    return 0
                now_mono = time.monotonic()
                last_enqueue = float(follower_last_enqueue_mono_by_clip.get(int(clip_idx), 0.0) or 0.0)
                if (
                    not force
                    and len(pending) < follower_stream_batch_size
                    and (now_mono - last_enqueue) < follower_stream_min_interval_sec
                ):
                    return 0
                if force:
                    batch = list(pending)
                    pending.clear()
                else:
                    batch = list(pending[:follower_stream_batch_size])
                    del pending[:follower_stream_batch_size]
                follower_last_enqueue_mono_by_clip[int(clip_idx)] = now_mono
                queued = _queue_follower_rows(
                    int(clip_idx),
                    batch,
                    reason=("final" if follower_start_after_pioneer else "stream"),
                )
                if queued <= 0 and pending:
                    follower_pending_by_clip[int(clip_idx)] = pending
                return queued

            def _provisional_found(row: dict, _current_rows: list[dict]):
                sec = self._cut_boundary_sec_from_row(row)
                if sec is not None and sec > 0.0:
                    provisional = _style_provisional_row(row)
                    with list_lock:
                        provisional_rows.append(provisional)
                        provisional_rows[:] = normalize_cut_boundaries(list(provisional_rows))
                        self._cut_boundary_provisional_rows = [dict(item) for item in provisional_rows]
                        preview_rows = [dict(item) for item in provisional_rows]
                        try:
                            clip_idx = int(provisional.get("clip_idx", 0) or 0)
                        except Exception:
                            clip_idx = 0
                        follower_pending_by_clip.setdefault(clip_idx, []).append(dict(provisional))
                    if realtime_preview_enabled:
                        self._ui_emit("_sig_preview_cut_boundary_scan_lines", preview_rows)
                    _maybe_flush_streaming_follower(clip_idx)
                    if is_audio_gain_boundary(provisional):
                        try:
                            get_logger().log(
                                f"  🟢 [컷 경계] 음성 임시선 후보: {float(sec):.3f}s "
                                f"(gain {float(provisional.get('audio_gain_db_delta', 0.0) or 0.0):+.1f}dB)"
                            )
                        except Exception:
                            pass

            def _found_verified(row: dict, _current_rows: list[dict]):
                _commit_follower_results([dict(row)], [], [dict(row)])

            def _prepare_relocated_provisional(row: dict) -> dict | None:
                sec = self._cut_boundary_sec_from_row(row)
                if sec is None or sec <= 0.0:
                    return None
                relocated = _style_provisional_row(row)
                relocated["status"] = "provisional"
                relocated["detector_stage"] = "follower"
                relocated["follower_relocated"] = True
                relocated["follower_active"] = False
                relocated["ui_label"] = "재배치"
                return relocated

            def _commit_follower_results(
                verified_rows: list[dict],
                relocated_rows: list[dict],
                checked_rows: list[dict],
                *,
                force_save: bool = False,
            ):
                verified_rows = [dict(row) for row in list(verified_rows or []) if isinstance(row, dict)]
                relocated_rows = [dict(row) for row in list(relocated_rows or []) if isinstance(row, dict)]
                verified_keys = {
                    self._cut_boundary_candidate_key(row)
                    for row in list(verified_rows or [])
                    if isinstance(row, dict)
                }
                checked_keys = {
                    self._cut_boundary_candidate_key(row)
                    for row in list(checked_rows or [])
                    if isinstance(row, dict)
                }
                checked_preview_rows = [
                    _checked_provisional_row(
                        row,
                        verified=self._cut_boundary_candidate_key(row) in verified_keys,
                    )
                    for row in list(checked_rows or [])
                    if isinstance(row, dict)
                ]
                verified_positions: list[tuple[int, float]] = []
                for row in verified_rows:
                    sec = self._cut_boundary_sec_from_row(row)
                    if sec is None:
                        continue
                    try:
                        clip_idx = int(row.get("clip_idx", 0) or 0)
                    except Exception:
                        clip_idx = 0
                    verified_positions.append((clip_idx, float(sec)))

                changed_detected = False
                changed_preview = False
                with list_lock:
                    if verified_rows:
                        detected[:] = normalize_cut_boundaries(list(detected) + verified_rows)
                        changed_detected = True

                    middle_review_rows = list(verified_rows or []) + list(relocated_rows or [])
                    middle_review_rows.extend(
                        row
                        for row in list(checked_preview_rows or [])
                        if isinstance(row, dict) and is_audio_gain_boundary(row)
                    )
                    changed_middle_review = _merge_reviewed_middle_rows(middle_review_rows)

                    if checked_keys or verified_positions or relocated_rows:
                        kept = []
                        for item in provisional_rows:
                            if not isinstance(item, dict):
                                kept.append(item)
                                continue
                            key = str(item.get("candidate_key") or self._cut_boundary_candidate_key(item))
                            try:
                                clip_idx = int(item.get("clip_idx", 0) or 0)
                            except Exception:
                                clip_idx = 0
                            try:
                                item_sec = float(item.get("timeline_sec", item.get("time", 0.0)) or 0.0)
                            except Exception:
                                item_sec = 0.0
                            near_verified = any(
                                old_clip_idx == clip_idx and abs(item_sec - sec) <= 0.50
                                for old_clip_idx, sec in verified_positions
                            )
                            if key in checked_keys or near_verified:
                                changed_preview = True
                                continue
                            kept.append(item)
                        provisional_rows[:] = kept

                    for relocated in relocated_rows:
                        try:
                            clip_idx = int(relocated.get("clip_idx", 0) or 0)
                        except Exception:
                            clip_idx = 0
                        try:
                            relocated_sec = float(relocated.get("timeline_sec", relocated.get("time", 0.0)) or 0.0)
                        except Exception:
                            relocated_sec = 0.0
                        kept = []
                        for item in provisional_rows:
                            try:
                                old_clip_idx = int(item.get("clip_idx", 0) or 0)
                            except Exception:
                                old_clip_idx = 0
                            try:
                                old_sec = float(item.get("timeline_sec", item.get("time", 0.0)) or 0.0)
                            except Exception:
                                old_sec = 0.0
                            item_status = str(item.get("status", "") or "").strip().lower() if isinstance(item, dict) else ""
                            if (
                                old_clip_idx == clip_idx
                                and abs(old_sec - relocated_sec) <= 0.75
                                and item_status != "checked"
                            ):
                                changed_preview = True
                                continue
                            kept.append(item)
                        provisional_rows[:] = kept
                        changed_preview = True

                    if changed_preview:
                        provisional_rows[:] = normalize_cut_boundaries(list(provisional_rows))
                    preview_rows = [dict(item) for item in provisional_rows]
                    reviewed_rows = [dict(item) for item in reviewed_middle_rows]
                    detected_rows = [dict(item) for item in detected]
                    detected_count = len(detected)
                    self._cut_boundary_provisional_rows = [dict(item) for item in provisional_rows]

                if changed_preview and realtime_preview_enabled:
                    self._ui_emit("_sig_preview_cut_boundary_scan_lines", preview_rows)
                middle_preview_source_rows = self._reviewed_cut_boundary_rows_for_middle_segments(
                    reviewed_rows,
                    detected_rows=detected_rows,
                )
                if changed_detected:
                    self._ui_emit("_sig_update_project_boundary_times", detected_rows)
                    self._ui_emit("_sig_refresh_cut_boundary_placeholder")
                if (changed_detected or changed_preview or changed_middle_review) and realtime_preview_enabled and middle_preview_source_rows:
                    middle_preview_rows = self._build_cut_boundary_topicless_rows(
                        middle_preview_source_rows,
                        files=list(files or []),
                        done=True,
                        prefer_all_frames=False,
                    )
                    if middle_preview_rows:
                        self._ui_emit("_sig_preview_cut_boundary_topicless_segments", middle_preview_rows)
                if changed_detected or changed_preview:
                    _save_detected_now(force=force_save)
                if changed_detected:
                    try:
                        self._emit_cut_boundary_count_to_sidebar(detected_count, done=False)
                    except Exception:
                        pass

            def _relocated_provisional_found(row: dict, _current_rows: list[dict]):
                relocated = _prepare_relocated_provisional(row)
                if relocated is None:
                    return
                _commit_follower_results([], [relocated], [])
                try:
                    sec = self._cut_boundary_sec_from_row(relocated)
                    get_logger().log(
                        f"  ▫️ [컷 경계] 임시선 재배치: {float(sec):.3f}s "
                        f"({relocated.get('provisional_mode', 'rollback')}, score {float(relocated.get('score', 0.0) or 0.0):.1f})"
                    )
                except Exception:
                    pass

            def _pioneer_completion(info: dict):
                try:
                    clip_no = int(info.get("clip_idx", 0) or 0) + 1
                except Exception:
                    clip_no = 1
                worker_total = max(1, int(info.get("worker_total", 1) or 1))
                worker_completed = max(0, int(info.get("worker_completed", 0) or 0))
                done = bool(info.get("done", False)) or worker_completed >= worker_total
                if done and not pioneer_done_by_clip.get(clip_no):
                    pioneer_done_by_clip[clip_no] = True

            def _follower_worker():
                nonlocal follower_checked_candidates, follower_verified_candidates
                try:
                    if follower_start_after_pioneer:
                        get_logger().log("  🚀 [컷 경계] 후발대 검증 워커 준비 완료: 선발대 완료 후 지연 처리합니다")
                    else:
                        get_logger().log("  🚀 [컷 경계] 후발대 검증 워커 준비 완료: 선발대 클립 완료 즉시 처리합니다")
                    processed_jobs = 0
                    while True:
                        job = follower_queue.get()
                        if job is None:
                            break
                        processed_jobs += 1
                        rows = [dict(row) for row in list(job.get("rows") or []) if isinstance(row, dict)]
                        if not job.get("path"):
                            continue
                        reason = str(job.get("reason") or "stream")
                        try:
                            reason_label = "병렬" if reason == "stream" else ("지연" if follower_start_after_pioneer else "잔여")
                            with follower_progress_lock:
                                total_for_log = max(
                                    int(job.get("total_after_queue", 0) or 0),
                                    int(follower_total_candidates or 0),
                                    len(rows),
                                )
                                checked_for_log = int(follower_checked_candidates or 0)
                            get_logger().log(
                                f"  🚀 [컷 경계] 파일 {int(job.get('clip_idx', 0) or 0) + 1}/{total_files} "
                                f"후발대 {reason_label} 검증 시작 "
                                f"({checked_for_log + 1}-{checked_for_log + len(rows)}/{total_for_log}, "
                                f"후보 {len(rows)}개)"
                            )
                        except Exception:
                            pass
                        if rows:
                            with list_lock:
                                changed = self._mark_cut_boundary_rows_following(provisional_rows, rows)
                                self._cut_boundary_provisional_rows = [dict(item) for item in provisional_rows]
                                preview_rows = [dict(item) for item in provisional_rows]
                            if changed:
                                if realtime_preview_enabled:
                                    self._ui_emit("_sig_preview_cut_boundary_scan_lines", preview_rows)
                                self._ui_emit(
                                    "_sig_editor_processing_stage",
                                    f"후발대 컷 경계 확인 중 ({len(rows)}개 배치)",
                                )
                            verified_batch: list[dict] = []
                            relocated_batch: list[dict] = []

                            def _collect_verified(row: dict, _current_rows: list[dict]):
                                if isinstance(row, dict):
                                    verified_batch.append(dict(row))

                            def _collect_relocated(row: dict, _current_rows: list[dict]):
                                relocated = _prepare_relocated_provisional(row)
                                if relocated is None:
                                    return
                                relocated_batch.append(relocated)
                                try:
                                    sec = self._cut_boundary_sec_from_row(relocated)
                                    get_logger().log(
                                        f"  ▫️ [컷 경계] 임시선 재배치: {float(sec):.3f}s "
                                        f"({relocated.get('provisional_mode', 'rollback')}, score {float(relocated.get('score', 0.0) or 0.0):.1f})"
                                    )
                                except Exception:
                                    pass

                            verify_settings = _follower_verify_settings(reason, len(rows))
                            returned_verified = verify_media_cut_boundary_rows(
                                job["path"],
                                rows,
                                clip_offset=job["offset"],
                                clip_idx=job["clip_idx"],
                                scan_profile=follower_scan_profile,
                                sample_positions=follower_scan_profile.get("positions", ()),
                                settings=verify_settings,
                                settings_preloaded=True,
                                found_callback=_collect_verified,
                                provisional_callback=_collect_relocated,
                            )
                            if not verified_batch:
                                verified_batch = [
                                    dict(row)
                                    for row in list(returned_verified or [])
                                    if isinstance(row, dict)
                                    and (row.get("verified") or row.get("visual_verify_skipped"))
                                ]
                            _commit_follower_results(
                                verified_batch,
                                relocated_batch,
                                rows,
                                force_save=(reason != "stream"),
                            )
                            with follower_progress_lock:
                                follower_checked_candidates += len(rows)
                                follower_verified_candidates += len(verified_batch)
                                checked_now = int(follower_checked_candidates or 0)
                                total_now = max(
                                    int(follower_total_candidates or 0),
                                    int(job.get("total_after_queue", 0) or 0),
                                    checked_now,
                                )
                                verified_now = int(follower_verified_candidates or 0)
                            pct_now = int(round((checked_now / float(max(1, total_now))) * 100.0))
                            self._ui_emit(
                                "_sig_editor_processing_stage",
                                f"후발대 컷 경계 확인 {checked_now}/{total_now} ({pct_now}%) · 확정 {verified_now}개",
                            )
                            try:
                                get_logger().log(
                                    f"  🎬 [후발대 진행] rollback 검증 {checked_now}/{total_now} "
                                    f"({pct_now}%) · 확정 {verified_now}개"
                                )
                            except Exception:
                                pass
                    with list_lock:
                        final_detected = [dict(item) for item in detected]
                        final_middle_source_rows = self._reviewed_cut_boundary_rows_for_middle_segments(
                            reviewed_middle_rows,
                            detected_rows=final_detected,
                        )
                    self._clear_completed_cut_boundary_provisionals(
                        project_path,
                        settings=settings,
                        detected=final_detected,
                        reviewed_rows=final_middle_source_rows,
                    )
                    self._save_cut_boundary_cache_for_start(files, settings, final_detected)
                    self._cut_boundary_prescan_completed = True
                    try:
                        self._ui_emit("_sig_editor_processing_stage", "컷 경계 중분류 세그먼트 확정 중")
                        self._force_cut_boundary_topicless_segments_to_project(
                            project_path,
                            final_detected,
                            files=list(files or []),
                            done=True,
                            middle_source_rows=(final_middle_source_rows or final_detected),
                            prefer_all_frames=False,
                        )
                    except Exception as exc:
                        get_logger().log(f"  ⚠️ [컷 경계] 최종 중분류 확정 실패: {exc}")
                    finally:
                        with list_lock:
                            provisional_rows[:] = []
                            self._cut_boundary_provisional_rows = []
                        self._ui_emit("_sig_set_cut_boundary_scan_active", False)
                        self._ui_emit("_sig_preview_cut_boundary_scan_lines", [])
                        try:
                            self._emit_cut_boundary_count_to_sidebar(len(final_detected), done=True)
                        except Exception:
                            pass
                    self._ui_emit(
                        "_sig_update_project_boundary_times",
                        [dict(row) for row in list(final_detected or []) if isinstance(row, dict)],
                    )
                    with follower_progress_lock:
                        checked_final = int(follower_checked_candidates or 0)
                        total_final = max(int(follower_total_candidates or 0), checked_final)
                        verified_final = int(follower_verified_candidates or 0)
                    if processed_jobs <= 0:
                        get_logger().log("  ✅ [컷 경계] 후발대 검증 완료: 확인할 후보 없음")
                    else:
                        get_logger().log(
                            f"  ✅ [컷 경계] 후발대 검증 완료: 후보 {checked_final}/{total_final}개 확인, "
                            f"정식 {verified_final}개 확정 ({processed_jobs}개 작업)"
                        )
                except Exception as exc:
                    get_logger().log(f"  ⚠️ [컷 경계] 후발대 검증 실패: {exc}")

            follower_thread: threading.Thread | None = None

            def _start_follower_thread(*, reason: str = "stream") -> threading.Thread | None:
                nonlocal follower_thread
                if follower_thread is not None:
                    return follower_thread
                if follower_start_delay_sec > 0.0 and reason != "stream":
                    time.sleep(follower_start_delay_sec)
                follower_thread = threading.Thread(
                    target=_follower_worker,
                    name="cut-boundary-follower-worker",
                    daemon=True,
                )
                self._cut_boundary_follower_thread = follower_thread
                follower_thread.start()
                return follower_thread

            if not follower_start_after_pioneer:
                _start_follower_thread(reason="stream")

            for idx, path in enumerate(list(files or [])):
                offset = 0.0
                if idx < len(clip_boundaries):
                    try:
                        offset = float(clip_boundaries[idx].get("start", 0.0) or 0.0)
                    except Exception:
                        offset = 0.0
                clip_offset_by_idx[idx] = float(offset or 0.0)
                detect_kwargs = dict(
                    clip_offset=offset,
                    clip_idx=idx,
                    sample_step_sec=provisional_step_sec,
                    threshold=float(settings.get("scan_cut_auto_threshold", settings.get("scan_cut_threshold", 24.0)) or 24.0),
                    progress_callback=_progress,
                    found_callback=_provisional_found,
                    completion_callback=_pioneer_completion,
                    settings=provisional_settings,
                    settings_preloaded=True,
                )
                rows = scan_media_cut_boundary_provisionals(
                    path,
                    **detect_kwargs,
                    scan_profile=provisional_scan_profile,
                    sample_positions=provisional_scan_profile.get("positions", ()),
                    sample_mask=provisional_scan_profile.get("mask", ""),
                )
                pending_queued = _maybe_flush_streaming_follower(idx, force=True)
                final_queued = _queue_follower_rows(
                    idx,
                    [dict(row) for row in list(rows or []) if isinstance(row, dict)],
                    reason="final",
                )
                queued_total = int(pending_queued or 0) + int(final_queued or 0)
                try:
                    get_logger().log(
                        f"  🚀 [컷 경계] 파일 {idx + 1}/{total_files} 선발대 완료 → 후발대 큐 전달 "
                        f"(잔여 후보 {queued_total}개 / 전체 {len(rows or [])}개)"
                    )
                except Exception:
                    pass

            with list_lock:
                if realtime_preview_enabled and provisional_rows:
                    self._ui_emit("_sig_preview_cut_boundary_scan_lines", [dict(item) for item in provisional_rows])
                self._cut_boundary_provisional_rows = [dict(item) for item in provisional_rows]
            if follower_start_after_pioneer:
                _start_follower_thread(reason="deferred")
            follower_queue.put(None)
            return detected
        except Exception as exc:
            try:
                follower_queue.put(None)
            except Exception:
                pass
            get_logger().log(f"  ⚠️ [컷 경계] 시작 전 자동 분석 실패: {exc}")
            return []
        finally:
            follower = getattr(self, "_cut_boundary_follower_thread", None)
            if follower is None or not follower.is_alive():
                self._ui_emit("_sig_set_cut_boundary_scan_active", False)

    def _split_by_saved_cut_boundaries(self, segments, *, offset: float = 0.0, context: str = "자막") -> list[dict]:
        """Split subtitle/STT rows so no row crosses a saved visual cut."""
        try:
            from core.cut_boundary import cut_boundary_enabled, split_segments_by_cut_boundaries
            from core.frame_time import frame_to_sec, sec_to_frame

            settings = load_settings()
            boundaries = self._project_cut_boundaries_for_pipeline()
            if offset:
                local = []
                offset = float(offset or 0.0)
                for item in boundaries:
                    row = dict(item)
                    fps = float(row.get("fps", row.get("timeline_frame_rate", row.get("frame_rate", 30.0))) or 30.0)
                    frame = row.get("timeline_frame", row.get("frame"))
                    if frame is None:
                        frame = sec_to_frame(float(row.get("timeline_sec", row.get("time", 0.0)) or 0.0), fps)
                    shifted_frame = int(frame) - sec_to_frame(offset, fps)
                    if shifted_frame <= 0:
                        continue
                    sec = frame_to_sec(shifted_frame, fps)
                    row["timeline_frame"] = shifted_frame
                    row["frame"] = shifted_frame
                    row["timeline_sec"] = sec
                    row["time"] = sec
                    local.append(row)
                boundaries = local
            if not boundaries:
                return [dict(seg) for seg in (segments or [])]
            result = split_segments_by_cut_boundaries(
                segments,
                boundaries,
                enabled=cut_boundary_enabled(settings),
            )
            if len(result) != len(segments or []):
                get_logger().log(f"  ✂️ [컷 경계] {context} {len(segments or [])}개 → {len(result)}개 절대 분할")
            return result
        except Exception as exc:
            get_logger().log(f"  ⚠️ [컷 경계] {context} 분할 실패, 기존 세그먼트 유지: {exc}")
            return [dict(seg) for seg in (segments or [])]

    def _magnetize_by_saved_cut_boundaries(
        self,
        segments,
        *,
        offset: float = 0.0,
        context: str = "자막",
        include_confirmed: bool = True,
        include_provisional: bool = True,
        provisional_window_sec: float = 0.32,
        confirmed_window_sec: float = 0.60,
    ) -> list[dict]:
        """Snap subtitle/STT rows to both provisional and confirmed saved cuts."""
        try:
            from core.cut_boundary import (
                cut_boundary_enabled,
                magnetize_segments_to_cut_boundaries,
            )
            from core.frame_time import frame_to_sec, sec_to_frame

            settings = load_settings()
            confirmed = self._project_cut_boundaries_for_pipeline() if include_confirmed else []
            provisional = self._project_cut_provisional_boundaries_for_pipeline() if include_provisional else []
            if offset:
                offset = float(offset or 0.0)

                def _shift(items):
                    out = []
                    for item in items:
                        row = dict(item)
                        fps = float(row.get("fps", row.get("timeline_frame_rate", row.get("frame_rate", 30.0))) or 30.0)
                        frame = row.get("timeline_frame", row.get("frame"))
                        if frame is None:
                            frame = sec_to_frame(float(row.get("timeline_sec", row.get("time", 0.0)) or 0.0), fps)
                        shifted_frame = int(frame) - sec_to_frame(offset, fps)
                        if shifted_frame <= 0:
                            continue
                        sec = frame_to_sec(shifted_frame, fps)
                        row["timeline_frame"] = shifted_frame
                        row["frame"] = shifted_frame
                        row["timeline_sec"] = sec
                        row["time"] = sec
                        out.append(row)
                    return out

                confirmed = _shift(confirmed)
                provisional = _shift(provisional)
            if not confirmed and not provisional:
                return [dict(seg) for seg in (segments or [])]
            return magnetize_segments_to_cut_boundaries(
                segments,
                confirmed_boundaries=confirmed,
                provisional_boundaries=provisional,
                enabled=cut_boundary_enabled(settings),
                provisional_window_sec=provisional_window_sec,
                confirmed_window_sec=confirmed_window_sec,
                min_duration_sec=0.05,
            )
        except Exception as exc:
            get_logger().log(f"  ⚠️ [컷 경계] {context} 스냅 실패, 기존 세그먼트 유지: {exc}")
            return [dict(seg) for seg in (segments or [])]
