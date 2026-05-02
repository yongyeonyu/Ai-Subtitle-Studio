# Version: 02.03.02
# Phase: PHASE1-B
"""
core/pipeline/pipeline_helpers.py
PipelineHelpersMixin — 백업 · 재시작 · 저장/내보내기 · 렌더링 · 화자분리 · ntfy · 프리페치 · 오디오 추출
"""
import os
import json
import threading
import traceback
import time

import config
from logger import get_logger
from core.audio.media_processor import VideoProcessor
from core.settings import load_settings, get_model_key


class PipelineHelpersMixin:
    """CoreBackend 에서 사용하는 공통 헬퍼 메서드 모음."""

    def _align_subtitle_segments_to_vad(self, segments, vad_segments, *, context: str = "자막") -> list[dict]:
        """VAD 음성 경계로 자막 시작/끝을 보정한 뒤 에디터로 넘깁니다."""
        out = [dict(seg) for seg in (segments or [])]
        if not out or not vad_segments:
            return out
        try:
            settings = load_settings()
        except Exception:
            settings = {}
        if not bool(settings.get("vad_post_stt_align_enabled", True)):
            return out

        try:
            from core.subtitle_quality.vad_alignment_checker import adjust_segments_to_vad_boundaries

            adjusted, adjusted_count = adjust_segments_to_vad_boundaries(
                out,
                vad_segments,
                max_shift_sec=float(settings.get("vad_post_stt_max_shift_sec", 0.7) or 0.7),
                edge_pad_sec=float(settings.get("vad_post_stt_edge_pad_sec", 0.04) or 0.04),
            )
            if adjusted_count:
                get_logger().log(f"  🎯 [VAD 후처리] {context} 자막 위치 {adjusted_count}개 보정 후 자막 메뉴로 전달")
            return adjusted
        except Exception as exc:
            get_logger().log(f"  ⚠️ [VAD 후처리] {context} 자막 위치 보정 실패: {exc}")
            return out

    def _project_cut_boundaries_for_pipeline(self) -> list[dict]:
        """Return saved visual cut boundaries from the current project file."""
        try:
            from core.cut_boundary import project_cut_boundaries

            ui = getattr(self, "ui", None)
            project_path = str(getattr(ui, "_current_project_path", "") or "")
            if not project_path or not os.path.exists(project_path):
                return []
            import json

            with open(project_path, "r", encoding="utf-8") as f:
                return project_cut_boundaries(json.load(f))
        except Exception:
            return []

    def _cut_boundary_cache_path_for_start(self, files: list[str], settings: dict) -> str:
        """Return reusable cut-boundary cache path for the current media/settings."""
        import hashlib
        try:
            import config
            cache_root = os.path.join(config.OUTPUT_DIR, "cut_boundary_cache")
        except Exception:
            cache_root = os.path.join("output", "cut_boundary_cache")

        os.makedirs(cache_root, exist_ok=True)

        payload = {
            "version": 2,
            "files": [],
            "settings": {
                "scan_cut_auto_sample_step_sec": settings.get("scan_cut_auto_sample_step_sec", 1.0),
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
                    "scan_cut_auto_sample_step_sec": settings.get("scan_cut_auto_sample_step_sec", 1.0),
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

            get_logger().log(
                f"  ▒ [컷 경계] 주제없음 회색 중분류 세그먼트 저장 "
                f"({len(rows)}개, done={bool(done)})"
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

        try:
            get_logger().log(f"  🟢 [컷 경계] 사이드바 상태 갱신: {status}")
        except Exception:
            pass


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
                detect_media_cut_boundaries,
                normalize_cut_boundaries,
                sync_project_cut_boundaries,
                cut_boundary_scan_profile,
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
            total_files = len(list(files or []))
            step_sec = max(0.25, float(settings.get("scan_cut_auto_sample_step_sec", 1.0) or 1.0))
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

            try:
                get_logger().log(
                    f"  🎚️ [컷 경계] 단계: {scan_profile.get('label')} "
                    f"(mask={scan_profile.get('mask')}, cells={len(scan_profile.get('positions', []) or [])}/9)"
                )
            except Exception:
                pass

            # 자동 사전 스캔은 사용자가 다른 버튼을 누를 수 있어야 하므로
            # 전역 scan_active=True 신호를 보내지 않는다.
            # 이 신호는 UI에서 버튼 비활성화/대기 커서를 유발할 수 있다.
            # self._ui_emit("_sig_set_cut_boundary_scan_active", True)

            def _save_detected_now():
                try:
                    with open(project_path, "r", encoding="utf-8") as f:
                        project = json.load(f)
                    project.setdefault("analysis", {})
                    project["analysis"]["cut_boundaries"] = list(detected)
                    sync_project_cut_boundaries(project, settings=settings)
                    with open(project_path, "w", encoding="utf-8") as f:
                        json.dump(project, f, ensure_ascii=False, indent=2)
                except Exception as exc:
                    get_logger().log(f"  ⚠️ [컷 경계] 중간 저장 실패: {exc}")

            def _progress(info: dict):
                try:
                    clip_no = int(info.get("clip_idx", 0) or 0) + 1
                except Exception:
                    clip_no = 1
                pct = int(info.get("percent", 0) or 0)
                ts = float(info.get("timestamp", 0.0) or 0.0)
                dur = float(info.get("duration", 0.0) or 0.0)
                found = int(info.get("detected", 0) or 0)
                try:
                    self._emit_cut_boundary_count_to_sidebar(found, percent=pct, done=False)
                except Exception:
                    pass
                next_ts = min(dur, ts + step_sec) if dur > 0.0 else (ts + step_sec)
                get_logger().log(
                    f"  └ [컷 경계] 파일 {clip_no}/{total_files} 스캔 중 {pct}% "
                    f"({ts:.1f}s / {dur:.1f}s, 감지 {found}개)"
                )
                clip_offset = 0.0
                if (clip_no - 1) < len(clip_boundaries):
                    try:
                        clip_offset = float(clip_boundaries[clip_no - 1].get("start", 0.0) or 0.0)
                    except Exception:
                        clip_offset = 0.0
                self._ui_emit("_sig_preview_cut_boundary_scan", clip_offset + ts, clip_offset + next_ts)

            def _found(row: dict, current_rows: list[dict]):
                detected[:] = normalize_cut_boundaries(list(detected) + [dict(row)])
                clip_no = int(row.get("clip_idx", 0) or 0) + 1
                sec = float(row.get("timeline_sec", row.get("time", 0.0)) or 0.0)
                get_logger().log(
                    f"  🎯 [컷 경계] 파일 {clip_no}/{total_files} 경계 감지 "
                    f"{sec:.3f}s (누적 {len(detected)}개)"
                )
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
                    if placeholder_rows:
                        get_logger().log(
                            f"  ▒ [컷 경계] 주제없음 회색 중분류 저장 "
                            f"({len(placeholder_rows)}개, done=False)"
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

            for idx, path in enumerate(list(files or [])):
                offset = 0.0
                if idx < len(clip_boundaries):
                    try:
                        offset = float(clip_boundaries[idx].get("start", 0.0) or 0.0)
                    except Exception:
                        offset = 0.0
                get_logger().log(
                    f"  🎬 [컷 경계] 파일 {idx + 1}/{total_files} 분석 시작: {os.path.basename(path)} "
                    f"(offset {offset:.1f}s)"
                )
                detect_kwargs = dict(
                    clip_offset=offset,
                    clip_idx=idx,
                    sample_step_sec=float(settings.get("scan_cut_auto_sample_step_sec", 1.0) or 1.0),
                    threshold=float(settings.get("scan_cut_auto_threshold", settings.get("scan_cut_threshold", 24.0)) or 24.0),
                    progress_callback=_progress,
                    found_callback=_found,
                )
                try:
                    rows = detect_media_cut_boundaries(
                        path,
                        **detect_kwargs,
                        scan_profile=scan_profile,
                        sample_positions=scan_profile.get("positions", ()),
                        sample_mask=scan_profile.get("mask", ""),
                    )
                except TypeError:
                    get_logger().log("  ⚠️ [컷 경계] detector가 level profile 인자를 지원하지 않아 기본 호출로 재시도합니다")
                    rows = detect_media_cut_boundaries(path, **detect_kwargs)
                get_logger().log(
                    f"  ✅ [컷 경계] 파일 {idx + 1}/{total_files} 분석 완료: {os.path.basename(path)} "
                    f"(감지 {len(rows)}개)"
                )
                detected[:] = normalize_cut_boundaries(list(detected) + list(rows))
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
            if detected:
                get_logger().log(f"  🎬 [컷 경계] 시작 전 자동 분석 완료 ({len(detected)}개)")
            else:
                get_logger().log("  🎬 [컷 경계] 시작 전 자동 분석 완료 (감지 없음)")
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

            settings = load_settings()
            boundaries = self._project_cut_boundaries_for_pipeline()
            if offset:
                local = []
                offset = float(offset or 0.0)
                for item in boundaries:
                    row = dict(item)
                    sec = float(row.get("timeline_sec", row.get("time", 0.0)) or 0.0) - offset
                    if sec > 0.0:
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

    def _ask_single_existing_subtitle(self, target_file) -> bool:
        """단일 클립에 기존 SRT가 있으면 사용 여부를 묻고, 미사용 시 백업 이동합니다."""
        try:
            from core.path_manager import get_srt_path
            from core.subtitle_existing import backup_existing_srt, validate_srt_duration
            from ui.dialogs.message_box import ask_yes_no, show_message
            from PyQt6.QtWidgets import QMessageBox

            srt_p = get_srt_path(target_file)
            if not srt_p or not os.path.exists(srt_p):
                return False

            ok, reason = validate_srt_duration(srt_p, target_file)
            if not ok:
                show_message(
                    self.ui,
                    "기존 자막 오류",
                    reason,
                    icon=QMessageBox.Icon.Warning,
                    buttons=QMessageBox.StandardButton.Ok,
                    default=QMessageBox.StandardButton.Ok,
                )
                backup_existing_srt(srt_p)
                return False

            use_existing = ask_yes_no(
                self.ui,
                "기존 자막 사용",
                "기존 자막을 사용하시겠습니까?",
            )
            if not use_existing:
                backup_existing_srt(srt_p)
            return use_existing
        except Exception:
            return False

    def _move_existing_srt_to_backup(self, target_file) -> bool:
        """기존 SRT를 자막백업 폴더로 이동합니다."""
        try:
            from core.subtitle_existing import backup_existing_srt
            return backup_existing_srt(target_file)
        except Exception as e:
            get_logger().log(f"⚠️ 기존 자막 백업 이동 실패: {e}")
            return False

    # ─── 백업 ────────────────────────────────────────────
    def _backup_existing(self, target_file):
        """기존 자막/MOV 파일 백업"""
        try:
            from core.path_manager import get_srt_path
            import datetime
            import shutil

            base_path = os.path.splitext(target_file)[0]
            srt_p = get_srt_path(target_file)
            mov_p = f"{base_path}_자막소스.mov"
            backup_dir = os.path.join(os.path.dirname(target_file), "자막백업")

            if os.path.exists(srt_p) or os.path.exists(mov_p):
                os.makedirs(backup_dir, exist_ok=True)
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                if os.path.exists(srt_p):
                    shutil.copy2(
                        srt_p,
                        os.path.join(backup_dir, f"{os.path.basename(srt_p)}.{timestamp}.bak"),
                    )
                if os.path.exists(mov_p):
                    shutil.copy2(
                        mov_p,
                        os.path.join(backup_dir, f"{os.path.basename(mov_p)}.{timestamp}.bak"),
                    )
                get_logger().log("📦 기존 자막 파일을 '자막백업' 폴더에 안전하게 복사(백업)했습니다.")
        except Exception as e:
            get_logger().log(f"⚠️ 백업 중 오류 발생 (무시하고 진행): {e}")

    # ─── 재시작 ──────────────────────────────────────────
    def _handle_restart(self, target_file):
        """재시작 시 에디터/SRT 초기화"""
        get_logger().log("\n🔄 현재 파일의 자막 생성을 처음부터 다시 시작합니다...")
        try:
            from core.path_manager import get_srt_path

            srt_p = get_srt_path(target_file)
            if os.path.exists(srt_p):
                moved = self._move_existing_srt_to_backup(target_file)
                if moved:
                    get_logger().log("    └ 📦 기존 자막 파일을 백업 후 제거했습니다. (새로 생성)")
                elif os.path.exists(srt_p):
                    os.remove(srt_p)
                    get_logger().log("    └ 🗑️ 기존 자막 파일을 삭제했습니다. (새로 생성)")

            def _clear_editor_main():
                ed = getattr(self.ui, "_editor_widget", None)
                if ed is None:
                    return
                try:
                    if hasattr(ed, "text_edit"):
                        ed.text_edit.blockSignals(True)
                        ed.text_edit.clear()
                        ed.text_edit.blockSignals(False)
                    if hasattr(ed, "timeline") and hasattr(ed.timeline, "canvas"):
                        ed.timeline.update_segments([], 0.0, getattr(ed.timeline.canvas, "total_duration", 0.0))
                        ed.timeline.set_playhead(0.0)
                    if hasattr(ed, "video_player"):
                        ed.video_player.set_context_segments([])
                        ed.video_player.seek(0.0)
                    if hasattr(ed, "_segment_queue"):
                        ed._segment_queue.clear()
                    ed._cached_segs = []
                    ed._active_seg_start = 0.0
                    ed._is_dirty = False
                except Exception as ex:
                    get_logger().log(f"    └ ⚠️ 에디터 초기화 중 오류: {ex}")

            from PyQt6.QtCore import QTimer as _QT

            _QT.singleShot(0, _clear_editor_main)
        except Exception as e:
            get_logger().log(f"    └ ⚠️ 초기화 중 오류: {e}")

    # ─── 저장 + 내보내기 ─────────────────────────────────
    def _save_and_export(self, target_file, queue_index, final_segments, is_auto_mode):
        """SRT 저장 + MOV 렌더링 + 완료 처리"""
        get_logger().log("\n  [STEP 5] 💾 SRT 저장 중...")
        try:
            from core.engine.subtitle_engine import save_srt
            from core.path_manager import get_srt_path

            srt_path = get_srt_path(target_file)
            save_srt(final_segments, srt_path, apply_offset=True)
            get_logger().log(f"✅ {os.path.basename(srt_path)} 저장 완료")

            is_video_export = False
            export_settings = {}
            try:
                try:
                    from ui.dialogs.export_dialog import _load_es
                except ImportError:
                    from ui.dialogs.export_dialog import _load_es
                export_settings = _load_es()
                is_video_export = export_settings.get("icloud", False)
            except Exception:
                pass

            base_name = os.path.splitext(os.path.basename(target_file))[0]
            current_idx = queue_index + 1
            total_cnt = len(self.files_to_process)

            if not is_video_export and getattr(self.ui, "_is_auto_pipeline", False):
                self._send_ntfy_notification(
                    title=f"📝 {config.APP_NAME} 알림",
                    message=f"[{current_idx}/{total_cnt}] {base_name}.srt 생성 완료!\n🎯 다음 작업으로 넘어갑니다.",
                    tags="memo,sparkles",
                )

            if hasattr(self.ui, "_sig_update_queue"):
                try:
                    self.ui._sig_update_queue.emit(queue_index, "✅ 자막출력(srt)", "", "", "")
                except RuntimeError:
                    pass

            # ── STEP 6: MOV 렌더링 ──
            if is_video_export:
                try:
                    get_logger().log(
                        "\n  [STEP 6] 🎥 투명 자막 영상(MOV) 백그라운드 렌더링 및 iCloud 백업 중..."
                    )
                    if hasattr(self.ui, "_sig_update_queue"):
                        self.ui._sig_update_queue.emit(
                            queue_index, "🎥 자막영상출력(mov)", "", "", ""
                        )
                    self._run_background_render(
                        srt_path, target_file, export_settings, current_idx, total_cnt
                    )
                except Exception as e:
                    get_logger().log(f"❌ MOV 렌더링 오류: {e}")
                    get_logger().log(traceback.format_exc())

            try:
                from core.auto_tracker import AutoTracker

                AutoTracker().mark_completed(target_file)
                if hasattr(self.ui, "mark_cloud_file_done"):
                    self.ui.mark_cloud_file_done(target_file)
            except Exception:
                pass

            if hasattr(self.ui, "_sig_update_queue"):
                try:
                    if is_auto_mode:
                        self.ui._sig_update_queue.emit(
                            queue_index, "완료 (다음파일)", "", "", ""
                        )
                    else:
                        self.ui._sig_update_queue.emit(
                            queue_index, "자막생성완료", "", "", ""
                        )
                except RuntimeError:
                    pass

        except Exception as e:
            get_logger().log(f"❌ 처리 실패: {e}")

    # ─── 렌더링 ──────────────────────────────────────────
    def _run_background_render(self, srt_path, target_file, s, current_idx=1, total_cnt=1):
        """MOV 렌더링 → renderer.py에 위임"""
        from core.renderer import render_subtitle_mov

        success = render_subtitle_mov(srt_path, target_file, s, current_idx, total_cnt)

        if success:
            base_name = os.path.splitext(os.path.basename(target_file))[0]
            if getattr(self.ui, "_is_auto_pipeline", False):
                self._send_ntfy_notification(
                    title=f"🎞️ {config.APP_NAME} 알림",
                    message=f"[{current_idx}/{total_cnt}] {base_name}.srt / {base_name}.mov 생성 완료!",
                    tags="film_projector,rocket",
                )

        return success

    # ─── 화자 분리 ───────────────────────────────────────
    def _reload_speaker_settings(self):
        s = load_settings()
        self.min_speakers = int(s.get("min_speakers", 1))
        self.max_speakers = int(s.get("max_speakers", 1))

    def _load_selected_model(self):
        s = load_settings()
        return s.get("selected_model", getattr(config, "OLLAMA_MODEL", "exaone3.5:7.8b"))

    def _prepare_speaker_map(self, audio_path):
        try:
            from core.audio.diarize import get_speaker_map

            self._speaker_map = get_speaker_map(
                audio_path, self.min_speakers, self.max_speakers
            )
        except Exception:
            self._speaker_map = []

    # ─── NTFY 알림 ───────────────────────────────────────
    def _send_ntfy_notification(self, title, message, tags=""):
        from core.notifier import send_ntfy

        send_ntfy(title, message, tags)

    # ─── 프리페치 ────────────────────────────────────────
    def _prefetch_audio_for_file(self, target_file):
        if not target_file or not self._active:
            return

        current_generation = self._prefetch_generation

        with self._prefetch_lock:
            if target_file in self._prefetch_cache:
                return
            if target_file in self._prefetch_threads:
                th = self._prefetch_threads[target_file]
                if th.is_alive():
                    return

        def _task():
            vp = VideoProcessor()
            try:
                res = vp.extract_audio(target_file)
                with self._prefetch_lock:
                    if current_generation == self._prefetch_generation:
                        self._prefetch_cache[target_file] = res
            except Exception as e:
                get_logger().log(
                    f"⚠️ 오디오 선추출 실패: {os.path.basename(target_file)} / {e}"
                )
                with self._prefetch_lock:
                    if current_generation == self._prefetch_generation:
                        self._prefetch_cache[target_file] = None
            finally:
                try:
                    vp.stop_transcribe()
                except Exception:
                    pass
                with self._prefetch_lock:
                    self._prefetch_threads.pop(target_file, None)

        th = threading.Thread(
            target=_task,
            daemon=True,
            name=f"prefetch-{os.path.basename(target_file)}",
        )
        with self._prefetch_lock:
            self._prefetch_threads[target_file] = th
        th.start()

    # ─── 오디오 추출 결과 ────────────────────────────────
    def _get_audio_extract_result(self, target_file):
        th = None
        with self._prefetch_lock:
            th = self._prefetch_threads.get(target_file)

        if th and th.is_alive():
            th.join()

        with self._prefetch_lock:
            cached = self._prefetch_cache.pop(target_file, None)

        if cached:
            return cached

        return self.video_processor.extract_audio(target_file)


# === PIPELINE FULL TOPICLESS FRAME SPLIT START ===

def _pipeline_topicless_middle_label(index: int) -> str:
    try:
        index = max(1, int(index))
    except Exception:
        index = 1

    letters = ""
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _pipeline_topicless_fps_from_detected(self, detected, files=None, default: float = 30.0) -> float:
    from core.frame_time import normalize_fps

    for row in list(detected or []):
        if not isinstance(row, dict):
            continue
        for key in ("fps", "frame_rate", "timeline_frame_rate"):
            try:
                value = float(row.get(key) or 0.0)
                if value > 1.0:
                    return normalize_fps(value)
            except Exception:
                pass

    # 컷이 아직 없어도 원본 영상 fps를 사용
    try:
        from core.media_info import probe_media
        for path in list(files or []):
            info = probe_media(path)
            fps = float(info.get("fps", 0.0) or 0.0)
            if fps > 1.0:
                return normalize_fps(fps)
    except Exception:
        pass

    return normalize_fps(default)


def _pipeline_topicless_frame_from_row(row, fps: float) -> int | None:
    from core.frame_time import sec_to_frame

    if isinstance(row, dict):
        for key in ("timeline_frame", "frame", "start_frame", "timeline_start_frame"):
            try:
                value = row.get(key)
                if value is not None:
                    frame = int(value)
                    if frame > 0:
                        return frame
            except Exception:
                pass

        for key in ("timeline_sec", "time", "start", "timeline_start"):
            try:
                sec = float(row.get(key) or 0.0)
                if sec > 0.0:
                    return sec_to_frame(sec, fps)
            except Exception:
                pass

    return None


def _pipeline_topicless_row(index: int, start_frame: int, end_frame: int, fps: float) -> dict:
    from core.frame_time import frame_to_sec

    start_frame = max(0, int(start_frame))
    end_frame = max(start_frame, int(end_frame))

    start = frame_to_sec(start_frame, fps)
    end = frame_to_sec(end_frame, fps)

    major_label = _pipeline_topicless_middle_label(index)
    internal_id = f"cut_topicless_middle_{major_label}"

    return {
        "id": major_label,
        "segment_id": major_label,
        "chapter_id": major_label,
        "major_id": major_label,

        "internal_id": internal_id,
        "source_id": internal_id,

        "fps": fps,
        "frame_rate": fps,
        "timeline_frame_rate": fps,
        "start_frame": start_frame,
        "end_frame": end_frame,
        "timeline_start_frame": start_frame,
        "timeline_end_frame": end_frame,
        "frame_range": {
            "unit": "frame",
            "start": start_frame,
            "end": end_frame,
            "timeline_frame_rate": fps,
        },

        "start": start,
        "end": end,
        "timeline_start": start,
        "timeline_end": end,

        "title": "주제없음",
        "name": "주제없음",
        "display_title": f"{major_label} 주제없음",
        "display_name": f"{major_label} 주제없음",
        "label": f"{major_label} 주제없음",

        "summary": "컷 경계 기반으로 자동 생성된 임시 중분류 세그먼트입니다.",
        "llm_summary": "",

        "tags": ["컷경계", "주제없음"],
        "source": "cut_boundary",
        "story_role": "topicless_placeholder",
        "narrative_function": "cut_boundary_placeholder",

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
    }


def _patched_build_cut_boundary_topicless_rows(self, detected, *, files=None, done: bool = False) -> list[dict]:
    """
    컷 경계 기반 회색 주제없음 중분류 rows 생성.

    컷 경계 체크 ON이면:
    - detected가 비어도 전체 A 주제없음 생성
    - detected가 늘어나면 frame 기준으로 A/B/C split
    """
    from core.frame_time import sec_to_frame

    fps = _pipeline_topicless_fps_from_detected(self, detected, files=files)

    duration = self._cut_boundary_placeholder_duration(files)
    duration_frame = 0
    try:
        if duration > 0.0:
            duration_frame = sec_to_frame(float(duration), fps)
    except Exception:
        duration_frame = 0

    cut_frames = []
    for row in list(detected or []):
        frame = _pipeline_topicless_frame_from_row(row, fps)
        if frame is not None and frame > 0:
            cut_frames.append(int(frame))

    cut_frames = sorted(set(cut_frames))

    # 컷이 아직 없어도 전체 A 생성
    if not cut_frames:
        if duration_frame > 0:
            return [_pipeline_topicless_row(1, 0, duration_frame, fps)]
        return []

    boundary_frames = [0] + cut_frames

    # duration을 알면 마지막 컷~영상끝 구간도 항상 생성
    if duration_frame > boundary_frames[-1]:
        boundary_frames.append(duration_frame)

    rows = []
    for i in range(len(boundary_frames) - 1):
        start_frame = int(boundary_frames[i])
        end_frame = int(boundary_frames[i + 1])
        if end_frame <= start_frame:
            continue
        rows.append(_pipeline_topicless_row(i + 1, start_frame, end_frame, fps))

    return rows


PipelineHelpersMixin._build_cut_boundary_topicless_rows = _patched_build_cut_boundary_topicless_rows

# === PIPELINE FULL TOPICLESS FRAME SPLIT END ===


# === PIPELINE TOPICLESS SPLIT LOG PATCH START ===

def _pipeline_topicless_split_log_emit(message: str) -> None:
    try:
        get_logger().log(message)
    except Exception:
        try:
            print(message, flush=True)
        except Exception:
            pass


def _pipeline_topicless_split_row_meta(row: dict) -> tuple[str, int, int, float, float, float]:
    try:
        label = str(row.get("major_id") or row.get("segment_id") or row.get("id") or "?")
    except Exception:
        label = "?"

    try:
        fps = float(row.get("fps", row.get("frame_rate", row.get("timeline_frame_rate", 30.0))) or 30.0)
    except Exception:
        fps = 30.0

    try:
        start_frame = int(row.get("timeline_start_frame", row.get("start_frame")))
    except Exception:
        try:
            start_frame = int(round(float(row.get("start", row.get("timeline_start", 0.0)) or 0.0) * fps))
        except Exception:
            start_frame = 0

    try:
        end_frame = int(row.get("timeline_end_frame", row.get("end_frame")))
    except Exception:
        try:
            end_frame = int(round(float(row.get("end", row.get("timeline_end", 0.0)) or 0.0) * fps))
        except Exception:
            end_frame = start_frame

    try:
        start_sec = float(row.get("start", row.get("timeline_start", start_frame / fps)) or 0.0)
    except Exception:
        start_sec = start_frame / fps

    try:
        end_sec = float(row.get("end", row.get("timeline_end", end_frame / fps)) or 0.0)
    except Exception:
        end_sec = end_frame / fps

    return label, start_frame, end_frame, start_sec, end_sec, fps


def _pipeline_log_topicless_split_rows(rows, *, context: str = "pipeline") -> None:
    rows = list(rows or [])
    if not rows:
        _pipeline_topicless_split_log_emit(f"  ▒ [컷 경계] split 없음 context={context}")
        return

    _pipeline_topicless_split_log_emit(
        f"  ▒ [컷 경계] split frame/time 로그 시작 context={context} count={len(rows)}"
    )

    for row in rows:
        if not isinstance(row, dict):
            continue

        label, start_frame, end_frame, start_sec, end_sec, fps = _pipeline_topicless_split_row_meta(row)
        title = str(row.get("title", row.get("name", "주제없음")) or "주제없음")
        dur_frame = max(0, int(end_frame) - int(start_frame))
        dur_sec = max(0.0, float(end_sec) - float(start_sec))

        _pipeline_topicless_split_log_emit(
            f"  ▒ [컷 경계] split {label} {title} "
            f"frame={start_frame}->{end_frame} "
            f"time={start_sec:.3f}s->{end_sec:.3f}s "
            f"dur={dur_frame}f/{dur_sec:.3f}s "
            f"fps={fps:.3f}"
        )


_pipeline_original_force_cut_boundary_topicless_segments_to_project = (
    PipelineHelpersMixin._force_cut_boundary_topicless_segments_to_project
)


def _patched_force_cut_boundary_topicless_segments_to_project_with_log(
    self,
    project_path: str,
    detected,
    *,
    files=None,
    done: bool = False,
):
    rows = _pipeline_original_force_cut_boundary_topicless_segments_to_project(
        self,
        project_path,
        detected,
        files=files,
        done=done,
    )

    try:
        _pipeline_log_topicless_split_rows(
            rows,
            context=f"force-save done={bool(done)} cuts={len(list(detected or []))}",
        )
    except Exception as exc:
        try:
            get_logger().log(f"  ⚠️ [컷 경계] split 로그 실패: {exc}")
        except Exception:
            pass

    return rows


PipelineHelpersMixin._force_cut_boundary_topicless_segments_to_project = (
    _patched_force_cut_boundary_topicless_segments_to_project_with_log
)

# === PIPELINE TOPICLESS SPLIT LOG PATCH END ===


# === PIPELINE VIDEO FPS TOPICLESS OVERRIDE START ===

def _pipeline_video_fps_from_files(files=None, default: float = 30.0) -> float:
    from core.frame_time import normalize_fps

    try:
        default = normalize_fps(float(default or 30.0))
    except Exception:
        default = 30.0

    try:
        from core.media_info import probe_media
        for path in list(files or []):
            if not path or not os.path.exists(str(path)):
                continue
            info = probe_media(str(path))
            fps = float(info.get("fps", 0.0) or 0.0)
            if fps > 1.0:
                return normalize_fps(fps)
    except Exception:
        pass

    return default


def _pipeline_topicless_fps_from_detected(self, detected=None, files=None, default: float = 30.0) -> float:
    from core.frame_time import normalize_fps

    # 1) detected row fps
    for row in list(detected or []):
        if not isinstance(row, dict):
            continue

        for key in ("fps", "frame_rate", "timeline_frame_rate", "source_fps", "video_fps"):
            try:
                fps = float(row.get(key) or 0.0)
                if fps > 1.0:
                    return normalize_fps(fps)
            except Exception:
                pass

        # 2) row source_path probe
        try:
            path = str(row.get("source_path", "") or row.get("clip_file", "") or "")
        except Exception:
            path = ""
        if path:
            fps = _pipeline_video_fps_from_files([path], default=default)
            if abs(float(fps) - float(default)) > 0.001 or fps > 30.1:
                return fps

    # 3) current files probe
    return _pipeline_video_fps_from_files(files, default=default)


def _pipeline_topicless_middle_label(index: int) -> str:
    try:
        index = max(1, int(index))
    except Exception:
        index = 1

    letters = ""
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _pipeline_topicless_frame_from_row(row, fps: float) -> int | None:
    from core.frame_time import sec_to_frame

    if isinstance(row, dict):
        for key in ("timeline_frame", "frame", "start_frame", "timeline_start_frame"):
            try:
                value = row.get(key)
                if value is not None:
                    frame = int(value)
                    if frame > 0:
                        return frame
            except Exception:
                pass

        for key in ("timeline_sec", "time", "start", "timeline_start"):
            try:
                sec = float(row.get(key) or 0.0)
                if sec > 0.0:
                    return sec_to_frame(sec, fps)
            except Exception:
                pass

    return None


def _pipeline_topicless_row(index: int, start_frame: int, end_frame: int, fps: float) -> dict:
    from core.frame_time import frame_to_sec

    start_frame = max(0, int(start_frame))
    end_frame = max(start_frame, int(end_frame))

    start = frame_to_sec(start_frame, fps)
    end = frame_to_sec(end_frame, fps)

    major_label = _pipeline_topicless_middle_label(index)
    internal_id = f"cut_topicless_middle_{major_label}"

    return {
        "id": major_label,
        "segment_id": major_label,
        "chapter_id": major_label,
        "major_id": major_label,

        "internal_id": internal_id,
        "source_id": internal_id,

        "fps": fps,
        "frame_rate": fps,
        "timeline_frame_rate": fps,
        "start_frame": start_frame,
        "end_frame": end_frame,
        "timeline_start_frame": start_frame,
        "timeline_end_frame": end_frame,
        "frame_range": {
            "unit": "frame",
            "start": start_frame,
            "end": end_frame,
            "timeline_frame_rate": fps,
        },

        "start": start,
        "end": end,
        "timeline_start": start,
        "timeline_end": end,

        "title": "주제없음",
        "name": "주제없음",
        "display_title": f"{major_label} 주제없음",
        "display_name": f"{major_label} 주제없음",
        "label": f"{major_label} 주제없음",

        "summary": "컷 경계 기반으로 자동 생성된 임시 중분류 세그먼트입니다.",
        "llm_summary": "",

        "tags": ["컷경계", "주제없음"],
        "source": "cut_boundary",
        "story_role": "topicless_placeholder",
        "narrative_function": "cut_boundary_placeholder",

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
    }


def _patched_build_cut_boundary_topicless_rows(self, detected, *, files=None, done: bool = False) -> list[dict]:
    from core.frame_time import sec_to_frame

    fps = _pipeline_topicless_fps_from_detected(self, detected, files=files)

    duration = self._cut_boundary_placeholder_duration(files)
    duration_frame = 0
    try:
        if duration > 0.0:
            duration_frame = sec_to_frame(float(duration), fps)
    except Exception:
        duration_frame = 0

    cut_frames = []
    for row in list(detected or []):
        frame = _pipeline_topicless_frame_from_row(row, fps)
        if frame is not None and frame > 0:
            cut_frames.append(int(frame))

    cut_frames = sorted(set(cut_frames))

    # 컷이 없어도 전체 A 생성
    if not cut_frames:
        if duration_frame > 0:
            rows = [_pipeline_topicless_row(1, 0, duration_frame, fps)]
        else:
            rows = []
    else:
        boundaries = [0] + cut_frames
        if duration_frame > boundaries[-1]:
            boundaries.append(duration_frame)

        rows = []
        for i in range(len(boundaries) - 1):
            start_frame = int(boundaries[i])
            end_frame = int(boundaries[i + 1])
            if end_frame <= start_frame:
                continue
            rows.append(_pipeline_topicless_row(i + 1, start_frame, end_frame, fps))

    try:
        get_logger().log(
            f"  ▒ [컷 경계] topicless fps={fps:.3f} "
            f"cuts={len(cut_frames)} duration_frame={duration_frame} rows={len(rows)}"
        )
        for row in rows:
            get_logger().log(
                f"  ▒ [컷 경계] split {row.get('major_id')} {row.get('title')} "
                f"frame={row.get('timeline_start_frame')}->{row.get('timeline_end_frame')} "
                f"time={float(row.get('timeline_start', 0.0) or 0.0):.3f}s->{float(row.get('timeline_end', 0.0) or 0.0):.3f}s "
                f"fps={fps:.3f}"
            )
    except Exception:
        pass

    return rows


PipelineHelpersMixin._build_cut_boundary_topicless_rows = _patched_build_cut_boundary_topicless_rows

# === PIPELINE VIDEO FPS TOPICLESS OVERRIDE END ===

