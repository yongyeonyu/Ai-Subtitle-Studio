# Version: 03.13.06
# Phase: PHASE1-B
"""
core/pipeline/cut_boundary_helpers.py
PipelineCutBoundaryMixin — 컷 경계 자동 분석 · 캐시 · 주제없음 플레이스홀더 · 분할/스냅 헬퍼
"""
import json
import os
import time

from core.runtime.logger import get_logger
from core.settings import load_settings


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
                with open(project_path, "r", encoding="utf-8") as f:
                    project = json.load(f)
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
            "version": 2,
            "files": [],
            "settings": {
                "scan_cut_auto_sample_step_sec": settings.get("scan_cut_auto_sample_step_sec", 2.0),
                "scan_cut_auto_threshold": settings.get("scan_cut_auto_threshold", settings.get("scan_cut_threshold", 24.0)),
                "scan_cut_threshold": settings.get("scan_cut_threshold", 24.0),
                "scan_cut_mode": settings.get("scan_cut_mode", ""),
                "scan_cut_boundary_level": settings.get("scan_cut_boundary_level", settings.get("cut_boundary_level", "medium")),
                "scan_cut_grid_mask": settings.get("scan_cut_grid_mask", ""),
            },
        }

        for p in list(files or []):
            try:
                st = os.stat(p)
                payload["files"].append({
                    "path": os.path.abspath(p),
                    "size": int(st.st_size),
                    "mtime_ns": int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))),
                })
            except Exception:
                payload["files"].append({
                    "path": os.path.abspath(str(p)),
                    "size": 0,
                    "mtime_ns": 0,
                })

        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        key = hashlib.sha256(raw).hexdigest()[:24]
        return os.path.join(cache_root, f"cut_boundaries_{key}.json")

    def _load_cut_boundary_cache_for_start(self, project_path: str, files: list[str], settings: dict) -> list[dict]:
        """Load cached cut boundaries and hydrate only project.analysis.cut_boundaries.

        IMPORTANT:
        - Never replace/move/copy the project file itself.
        - Only inject cached analysis.cut_boundaries into the current project.
        """
        try:
            from core.cut_boundary import normalize_cut_boundaries, sync_project_cut_boundaries

            cache_path = self._cut_boundary_cache_path_for_start(files, settings)
            if not os.path.exists(cache_path):
                return []

            with open(cache_path, "r", encoding="utf-8") as f:
                payload = json.load(f)

            analysis = payload.get("analysis", {}) if isinstance(payload, dict) else {}
            rows = analysis.get("cut_boundaries", [])

            # Backward compatibility with older cache format
            if not rows:
                rows = payload.get("cut_boundaries", []) if isinstance(payload, dict) else []

            rows = normalize_cut_boundaries(rows or [])
            if not rows:
                return []

            # ✅ 핵심: 현재 프로젝트 파일은 그대로 두고 analysis.cut_boundaries만 주입
            if project_path and os.path.exists(project_path):
                with open(project_path, "r", encoding="utf-8") as f:
                    project = json.load(f)

                project.setdefault("analysis", {})
                project["analysis"]["cut_boundaries"] = list(rows)
                project["analysis"]["cut_boundary_prescan_done"] = True
                project["analysis"]["cut_boundary_cache_path"] = cache_path
                project["analysis"]["cut_boundary_cache_type"] = "cut_boundaries_only"

                sync_project_cut_boundaries(project, settings=settings)

                with open(project_path, "w", encoding="utf-8") as f:
                    json.dump(project, f, ensure_ascii=False, indent=2)

            get_logger().log(
                f"  ♻️ [컷 경계] 캐시 재사용: {len(rows)}개 "
                f"(analysis.cut_boundaries only, {cache_path})"
            )
            self._ui_emit("_sig_refresh_cut_boundary_placeholder")
            return rows
        except Exception as exc:
            get_logger().log(f"  ⚠️ [컷 경계] 캐시 불러오기 실패: {exc}")
            return []

    def _save_cut_boundary_cache_for_start(self, files: list[str], settings: dict, rows: list[dict]) -> None:
        """Save only cut-boundary analysis data for future reuse.

        IMPORTANT:
        - Do NOT move/copy the actual project file into cache.
        - The project file remains the source of truth for the current work.
        - Cache stores only analysis.cut_boundaries-compatible rows.
        """
        try:
            import time
            cache_path = self._cut_boundary_cache_path_for_start(files, settings)

            payload = {
                "version": 2,
                "created_at": time.time(),
                "cache_type": "cut_boundaries_only",
                "files": [],
                "settings": {
                    "scan_cut_auto_sample_step_sec": settings.get("scan_cut_auto_sample_step_sec", 2.0),
                    "scan_cut_auto_threshold": settings.get("scan_cut_auto_threshold", settings.get("scan_cut_threshold", 24.0)),
                    "scan_cut_threshold": settings.get("scan_cut_threshold", 24.0),
                    "scan_cut_mode": settings.get("scan_cut_mode", ""),
                "scan_cut_boundary_level": settings.get("scan_cut_boundary_level", settings.get("cut_boundary_level", "medium")),
                "scan_cut_grid_mask": settings.get("scan_cut_grid_mask", ""),
                },
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
                    })
                except Exception:
                    payload["files"].append({
                        "path": os.path.abspath(str(p)),
                        "size": 0,
                        "mtime_ns": 0,
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
        except Exception as exc:
            get_logger().log(f"  ⚠️ [컷 경계] STT 시작 전 대기 실패: {exc}")


    def _cut_boundary_sec_from_row(self, row) -> float | None:
        try:
            if isinstance(row, dict):
                return float(row.get("timeline_sec", row.get("time", row.get("start", 0.0))) or 0.0)
            return float(row)
        except Exception:
            return None

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

    def _build_cut_boundary_topicless_rows(self, detected, *, files=None, done: bool = False) -> list[dict]:
        """Build gray middle-level topicless rows from detected cut boundaries.

        During scan:
        - if first cut exists, immediately create 00:00~first_cut.

        After full scan:
        - also include last_cut~video_end.
        """
        cuts = []
        for row in list(detected or []):
            sec = self._cut_boundary_sec_from_row(row)
            if sec is not None and sec > 0.0:
                cuts.append(round(float(sec), 3))

        cuts = sorted(set(cuts))
        if not cuts:
            return []

        duration = self._cut_boundary_placeholder_duration(files)
        boundaries = [0.0] + cuts

        if done and duration > boundaries[-1]:
            boundaries.append(round(duration, 3))

        rows = []
        for i in range(len(boundaries) - 1):
            start = float(boundaries[i])
            end = float(boundaries[i + 1])
            if end <= start:
                continue

            seg_id = f"cut_topicless_middle_{i + 1:03d}"
            rows.append({
                "id": seg_id,
                "segment_id": seg_id,
                "chapter_id": seg_id,
                "major_id": seg_id,

                "start": round(start, 3),
                "end": round(end, 3),

                "title": "주제없음",
                "name": "주제없음",
                "summary": "컷 경계 기반으로 자동 생성된 임시 중분류 세그먼트입니다.",
                "llm_summary": "",

                "tags": ["컷경계", "주제없음"],
                "source": "cut_boundary",
                "story_role": "topicless_placeholder",
                "narrative_function": "cut_boundary_placeholder",

                # UI가 어느 키를 보든 회색 placeholder로 인식할 수 있게 넓게 저장
                "level": "middle",
                "segment_type": "middle",
                "roughcut_level": "middle",
                "category": "middle",
                "is_middle_segment": True,

                "is_topicless_placeholder": True,
                "is_cut_boundary_placeholder": True,
                "topicless": True,

                "color_role": "topicless",
                "display_color": "gray",
                "ui_color": "gray",
                "color": "#9CA3AF",

                "needs_review": True,
                "status": "needs_review",
                "safety": "acceptable",
                "importance": 0.0,
                "importance_score": 0.0,
                "boundary_confidence": 1.0,

                "can_move": True,
                "can_trim": True,
                "can_remove": True,
                "move_risk": "low",
                "dependencies": [],
            })

        return rows

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
                detected,
                files=list(files or []),
                done=bool(done),
            )
            if not rows:
                return []

            with open(project_path, "r", encoding="utf-8") as f:
                project = json.load(f)

            project.setdefault("analysis", {})
            analysis = project["analysis"]

            # 원본 컷 경계
            analysis["cut_boundaries"] = list(detected or [])

            # UI/러프컷 로더가 어떤 이름을 보든 찾을 수 있게 중복 저장
            analysis["cut_boundary_topicless_middle_segments"] = list(rows)
            analysis["topicless_middle_segments"] = list(rows)
            analysis["roughcut_topicless_segments"] = list(rows)
            analysis["middle_segments"] = list(rows)

            # roughcut 계열 저장소에도 placeholder-only 상태면 즉시 반영
            for key in ("roughcut", "roughcut_draft", "roughcut_result"):
                box = project.setdefault(key, {})
                if isinstance(box, dict) and self._placeholder_rows_can_be_overwritten(box.get("segments", [])):
                    box["segments"] = list(rows)
                    box["schema_version"] = "roughcut_result.v2"
                    box["draft_state"] = {"status": "review"}

            # 일부 UI가 top-level segments를 볼 수 있어 보조 저장
            if self._placeholder_rows_can_be_overwritten(project.get("roughcut_segments", [])):
                project["roughcut_segments"] = list(rows)
            if self._placeholder_rows_can_be_overwritten(project.get("middle_segments", [])):
                project["middle_segments"] = list(rows)

            with open(project_path, "w", encoding="utf-8") as f:
                json.dump(project, f, ensure_ascii=False, indent=2)

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
                get_logger().log("  🎬 [컷 경계] 이미 자동 분석이 진행 중입니다")
                return []

            def _worker():
                try:
                    self._auto_scan_cut_boundaries_for_start_sync(project_path, list(files or []))
                except Exception as exc:
                    try:
                        get_logger().log(f"  ⚠️ [컷 경계] 백그라운드 자동 분석 실패: {exc}")
                    except Exception:
                        pass

            thread = threading.Thread(
                target=_worker,
                name="cut-boundary-prescan-worker",
                daemon=True,
            )
            self._cut_boundary_prescan_thread = thread
            thread.start()
            get_logger().log("  🎬 [컷 경계] 백그라운드 자동 분석 시작")
            return []
        except Exception as exc:
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

            settings = load_settings()
            try:
                scan_profile = cut_boundary_scan_profile(settings)
            except Exception:
                scan_profile = {"level": "medium", "label": "중간 - 9개 중 꽉찬 십자가 5개", "mask": "x5", "positions": (0, 2, 4, 6, 8)}
            if not cut_boundary_enabled(settings):
                get_logger().log("  🎬 [컷 경계] 비활성화되어 있어 분석을 건너뜁니다")
                return []
            if not project_path or not os.path.exists(project_path):
                get_logger().log("  ⚠️ [컷 경계] 프로젝트 경로가 없어 분석을 건너뜁니다")
                return []

            cached = self._load_cut_boundary_cache_for_start(project_path, files, settings)
            if cached:
                return cached

            clip_boundaries = list(getattr(self.ui, "_multiclip_boundaries", []) or [])
            detected: list[dict] = []
            provisional_times: list[float] = []
            provisional_rows: list[dict] = []
            follower_jobs: list[dict] = []
            self._cut_boundary_provisional_rows = []
            total_files = len(list(files or []))
            progress_preview_interval_sec = 0.18
            progress_log_interval_sec = 0.75
            provisional_emit_interval_sec = 0.0
            last_preview_emit_mono = 0.0
            last_progress_log_mono = 0.0
            last_provisional_emit_mono = 0.0
            pioneer_done_by_clip: dict[int, bool] = {}
            pioneer_progress_by_clip: dict[int, dict[int, int]] = {}
            last_logged_progress_pct_by_clip: dict[int, int] = {}
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
            # CUT_BOUNDARY_FULL_TOPICLESS_INIT_V1
            # 컷 경계 체크가 켜져 있으면 스캔 시작 즉시 전체 A 주제없음 세그먼트를 만든다.
            # 이후 verified cut이 들어올 때마다 frame 기준으로 A/B/C split 된다.
            try:
                self._force_cut_boundary_topicless_segments_to_project(
                    project_path,
                    [],
                    files=list(files or []),
                    done=False,
                )
                self._ui_emit("_sig_refresh_cut_boundary_placeholder")
                get_logger().log("  ▒ [컷 경계] 전체 주제없음 회색 중분류 초기화 (A)")
            except Exception as exc:
                get_logger().log(f"  ⚠️ [컷 경계] 전체 주제없음 초기화 실패: {exc}")

            self._ui_emit("_sig_set_cut_boundary_scan_active", True)

            def _save_detected_now():
                try:
                    with open(project_path, "r", encoding="utf-8") as f:
                        project = json.load(f)
                    project.setdefault("analysis", {})
                    project["analysis"]["cut_boundaries"] = list(detected)
                    project["analysis"]["cut_boundary_provisional_boundaries"] = list(provisional_rows)
                    sync_project_cut_boundaries(
                        project,
                        settings=settings,
                        provisional_boundaries=list(provisional_rows),
                    )
                    with open(project_path, "w", encoding="utf-8") as f:
                        json.dump(project, f, ensure_ascii=False, indent=2)
                except Exception as exc:
                    get_logger().log(f"  ⚠️ [컷 경계] 중간 저장 실패: {exc}")

            def _progress(info: dict):
                nonlocal last_preview_emit_mono, last_progress_log_mono
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
                    worker_total = max(1, int(info.get("worker_total", 4) or 4))
                except Exception:
                    worker_total = 4
                try:
                    worker_pct = int(info.get("worker_percent", pct) or pct)
                except Exception:
                    worker_pct = pct
                clip_progress = pioneer_progress_by_clip.setdefault(clip_no, {})
                clip_progress[worker_idx] = max(0, min(100, worker_pct))
                aggregate_pct = int(round(sum(clip_progress.values()) / float(max(1, worker_total))))
                try:
                    self._emit_cut_boundary_count_to_sidebar(found, percent=aggregate_pct, done=False)
                except Exception:
                    pass
                now_mono = time.monotonic()
                next_ts = min(dur, ts + step_sec) if dur > 0.0 else (ts + step_sec)
                clip_offset = 0.0
                if (clip_no - 1) < len(clip_boundaries):
                    try:
                        clip_offset = float(clip_boundaries[clip_no - 1].get("start", 0.0) or 0.0)
                    except Exception:
                        clip_offset = 0.0
                if (now_mono - last_preview_emit_mono) >= progress_preview_interval_sec or pct >= 100:
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

            def _provisional_found(row: dict, current_rows: list[dict]):
                sec = self._cut_boundary_sec_from_row(row)
                if sec is not None and sec > 0.0:
                    provisional = dict(row)
                    provisional["status"] = "provisional"
                    provisional_rows.append(provisional)
                    provisional_rows[:] = normalize_cut_boundaries(list(provisional_rows))
                    self._cut_boundary_provisional_rows = [dict(item) for item in provisional_rows]
                    preview_rows = [dict(item) for item in provisional_rows]
                    self._ui_emit("_sig_preview_cut_boundary_scan_lines", preview_rows)

            def _found_verified(row: dict, current_rows: list[dict]):
                detected[:] = normalize_cut_boundaries(list(detected) + [dict(row)])
                provisional_sec = self._cut_boundary_sec_from_row(row)
                if provisional_sec is not None:
                    updated = False
                    for item in provisional_rows:
                        try:
                            item_sec = float(item.get("timeline_sec", item.get("time", 0.0)) or 0.0)
                        except Exception:
                            continue
                        if abs(item_sec - float(provisional_sec)) <= 0.001:
                            item.update(dict(row))
                            item["status"] = "verified"
                            updated = True
                    if not updated:
                        verified_row = dict(row)
                        verified_row["status"] = "verified"
                        provisional_rows.append(verified_row)
                    provisional_rows[:] = normalize_cut_boundaries(list(provisional_rows))
                preview_rows = [dict(item) for item in provisional_rows]
                verified_preview = dict(row)
                verified_preview["status"] = "verified"
                provisional_rows[:] = normalize_cut_boundaries(list(preview_rows) + [verified_preview])
                preview_rows = [dict(item) for item in provisional_rows]
                self._cut_boundary_provisional_rows = [dict(item) for item in provisional_rows]
                self._ui_emit("_sig_preview_cut_boundary_scan_lines", preview_rows)
                _save_detected_now()
                # CUT_TOPICLESS_GRAY_FIX_FOUND_V2
                try:
                    from core.roughcut.cut_boundary_placeholder import apply_topicless_placeholders_to_project
                    placeholder_rows = apply_topicless_placeholders_to_project(
                        project_path,
                        detected,
                        media_duration=None,
                        include_trailing=False,
                    )
                except Exception as exc:
                    get_logger().log(f"  ⚠️ [컷 경계] 주제없음 회색 중분류 저장 실패: {exc}")

                # ✅ 컷 경계 발견 즉시 회색 주제없음 중분류 세그먼트 생성
                try:
                    self._force_cut_boundary_topicless_segments_to_project(
                        project_path,
                        detected,
                        files=list(files or []),
                        done=False,
                    )
                except Exception as exc:
                    get_logger().log(f"  ⚠️ [컷 경계] 즉시 중분류 생성 실패: {exc}")

                # ✅ 왼쪽 사이드바 현재 진행 표시를 "1 컷 경계" 형태로 갱신
                try:
                    self._emit_cut_boundary_count_to_sidebar(len(detected), done=False)
                except Exception:
                    pass

                # 첫 번째 컷 경계가 발견되면 즉시 00:00~첫 경계 구간의
                # "주제없음/컷경계" 중분류 placeholder를 갱신한다.
                self._ui_emit("_sig_refresh_cut_boundary_placeholder")
                try:
                    self._ui_emit("_sig_refresh_cut_boundary_placeholder")
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

            for idx, path in enumerate(list(files or [])):
                offset = 0.0
                if idx < len(clip_boundaries):
                    try:
                        offset = float(clip_boundaries[idx].get("start", 0.0) or 0.0)
                    except Exception:
                        offset = 0.0
                detect_kwargs = dict(
                    clip_offset=offset,
                    clip_idx=idx,
                    sample_step_sec=step_sec,
                    threshold=float(settings.get("scan_cut_auto_threshold", settings.get("scan_cut_threshold", 24.0)) or 24.0),
                    progress_callback=_progress,
                    found_callback=_provisional_found,
                    completion_callback=_pioneer_completion,
                )
                rows = scan_media_cut_boundary_provisionals(
                    path,
                    **detect_kwargs,
                    scan_profile=scan_profile,
                    sample_positions=scan_profile.get("positions", ()),
                    sample_mask=scan_profile.get("mask", ""),
                )
                follower_jobs.append(
                    {
                        "path": path,
                        "clip_idx": idx,
                        "offset": offset,
                        "rows": list(rows or []),
                    }
                )

            self._ui_emit("_sig_set_cut_boundary_scan_active", False)
            if provisional_rows:
                self._ui_emit("_sig_preview_cut_boundary_scan_lines", [dict(item) for item in provisional_rows])
            self._cut_boundary_provisional_rows = [dict(item) for item in provisional_rows]

            def _follower_worker():
                try:
                    for job in follower_jobs:
                        verified_rows = verify_media_cut_boundary_rows(
                            job["path"],
                            job["rows"],
                            clip_offset=job["offset"],
                            clip_idx=job["clip_idx"],
                            scan_profile=scan_profile,
                            sample_positions=scan_profile.get("positions", ()),
                            settings=settings,
                            found_callback=_found_verified,
                        )
                    _save_detected_now()
                    try:
                        self._force_cut_boundary_topicless_segments_to_project(
                            project_path,
                            detected,
                            files=list(files or []),
                            done=True,
                        )
                        self._emit_cut_boundary_count_to_sidebar(len(detected), done=True)
                    except Exception as exc:
                        get_logger().log(f"  ⚠️ [컷 경계] 최종 중분류 확정 실패: {exc}")
                    self._ui_emit(
                        "_sig_update_project_boundary_times",
                        [float(row.get("timeline_sec", row.get("time", 0.0)) or 0.0) for row in detected],
                    )
                except Exception as exc:
                    get_logger().log(f"  ⚠️ [컷 경계] 후발대 검증 실패: {exc}")

            import threading
            follower_thread = threading.Thread(
                target=_follower_worker,
                name="cut-boundary-follower-worker",
                daemon=True,
            )
            self._cut_boundary_follower_thread = follower_thread
            follower_thread.start()
            return detected
        except Exception as exc:
            get_logger().log(f"  ⚠️ [컷 경계] 시작 전 자동 분석 실패: {exc}")
            return []
        finally:
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

    def _magnetize_by_saved_cut_boundaries(self, segments, *, offset: float = 0.0, context: str = "자막") -> list[dict]:
        """Snap subtitle/STT rows to both provisional and confirmed saved cuts."""
        try:
            from core.cut_boundary import (
                cut_boundary_enabled,
                magnetize_segments_to_cut_boundaries,
            )
            from core.frame_time import frame_to_sec, sec_to_frame

            settings = load_settings()
            confirmed = self._project_cut_boundaries_for_pipeline()
            provisional = self._project_cut_provisional_boundaries_for_pipeline()
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
                provisional_window_sec=0.32,
                confirmed_window_sec=0.60,
                min_duration_sec=0.05,
            )
        except Exception as exc:
            get_logger().log(f"  ⚠️ [컷 경계] {context} 스냅 실패, 기존 세그먼트 유지: {exc}")
            return [dict(seg) for seg in (segments or [])]
