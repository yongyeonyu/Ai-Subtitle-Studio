# Version: 03.14.34
# Phase: PHASE1-B
"""
core/pipeline/pipeline_helpers.py
PipelineHelpersMixin — VAD 정렬 · 백업 · 재시작 · 저장/내보내기 · 렌더링 · 화자분리 · ntfy · 프리페치 · 오디오 추출
"""
import os
import re
import threading
import traceback

from core.project.project_runtime_capture import collect_editor_project_aux_state
from core.runtime import config
from core.runtime.logger import get_logger
from core.audio.media_processor import VideoProcessor
from core.platform_compat import ffmpeg_binary
from core.speaker_profile_settings import automatic_speaker_ceiling, speaker_diarization_auto_enabled
from core.settings import load_settings
from core.pipeline.cut_boundary_helpers import PipelineCutBoundaryMixin
from ui.queue.queue_formatting import (
    build_queue_header_payload,
    build_queue_status_payload,
)
from ui.project.project_session_runtime import attach_project_session


class PipelineHelpersMixin(PipelineCutBoundaryMixin):
    """CoreBackend 에서 사용하는 공통 헬퍼 메서드 모음."""

    @staticmethod
    def _normalize_runtime_speaker_id(value) -> str:
        speaker = str(value or "").strip()
        if speaker.startswith("SPEAKER_"):
            speaker = speaker.replace("SPEAKER_", "", 1)
        return speaker or "00"

    def _dialogue_turn_speaker_pair(self) -> tuple[str, str]:
        try:
            settings = load_settings()
        except Exception:
            settings = {}
        first = self._normalize_runtime_speaker_id(settings.get("spk1_id", "00"))
        second = self._normalize_runtime_speaker_id(settings.get("spk2_id", "01"))
        if second == first:
            second = "01" if first != "01" else "02"
        return first, second

    def _runtime_speaker_limits(self) -> tuple[int, int]:
        try:
            min_speakers = int(
                getattr(self, "_effective_min_speakers", getattr(self, "min_speakers", 1)) or 1
            )
        except Exception:
            min_speakers = 1
        try:
            max_speakers = int(
                getattr(self, "_effective_max_speakers", getattr(self, "max_speakers", min_speakers)) or min_speakers
            )
        except Exception:
            max_speakers = min_speakers
        min_speakers = max(1, min_speakers)
        max_speakers = max(min_speakers, max_speakers)
        return min_speakers, max_speakers

    def _speaker_diarization_enabled(self) -> bool:
        _min_speakers, max_speakers = self._runtime_speaker_limits()
        return max_speakers > 1

    def _speaker_auto_processing_enabled(self) -> bool:
        return bool(getattr(self, "_speaker_auto_enabled", True) or self._speaker_diarization_enabled())

    def _apply_speaker_preflight_runtime_override(
        self,
        speaker_preflight: dict | None = None,
    ) -> tuple[int, int]:
        base_min = max(1, int(getattr(self, "min_speakers", 1) or 1))
        base_max = max(base_min, int(getattr(self, "max_speakers", base_min) or base_min))
        effective_min = base_min
        effective_max = base_max
        preflight = dict(speaker_preflight or getattr(self, "_autopilot_speaker_preflight", {}) or {})
        if bool(preflight.get("enabled", True)):
            estimated = max(1, int(preflight.get("estimated_speaker_count", base_max) or base_max))
            lane = str(preflight.get("lane", "") or "")
            if estimated >= 2 and lane in {"sample_check", "targeted_diarization"}:
                try:
                    settings = load_settings()
                except Exception:
                    settings = {}
                auto_ceiling = automatic_speaker_ceiling(settings)
                effective_max = min(3, max(effective_max, estimated, auto_ceiling))
        self._effective_min_speakers = min(effective_min, effective_max)
        self._effective_max_speakers = effective_max
        if effective_max > base_max:
            get_logger().log(
                "🗣️ [AutoPilot 화자] "
                f"자동 화자 모드에서 이번 구간은 {effective_max}명 대화 가능성이 높아 "
                "국소 화자 분리를 활성화합니다."
            )
        return self._effective_min_speakers, self._effective_max_speakers

    @staticmethod
    def _inline_dialogue_turns(text: str, *, allow_missing_leading_marker: bool = False) -> list[str]:
        compact = re.sub(r"\s+", " ", str(text or "").replace("\n", " ")).strip()
        if not compact.startswith("-"):
            if not allow_missing_leading_marker or not re.search(r"\s-\s*\S", compact):
                return []
            compact = f"- {compact}"
        turns = [
            match.group(1).strip()
            for match in re.finditer(r"(?:^|\s)-\s*([^-]+?)(?=\s+-\s*\S|$)", compact)
            if match.group(1).strip()
        ]
        if len(turns) != 2:
            turns = [part.lstrip("-").strip() for part in re.split(r"\s+-\s*", compact) if part.strip()]
        turns = [turn for turn in turns if turn]
        if len(turns) != 2:
            return []
        return turns

    def _speaker_sequence_for_range(
        self,
        start_t: float,
        end_t: float,
        speaker_map: list[dict] | None = None,
    ) -> list[str]:
        start_sec = float(start_t or 0.0)
        end_sec = max(start_sec, float(end_t or start_sec))
        sequence: list[str] = []
        for item in sorted(list(speaker_map or []), key=lambda row: (float(row.get("start", 0.0) or 0.0), float(row.get("end", 0.0) or 0.0))):
            try:
                seg_start = float(item.get("start", 0.0) or 0.0)
                seg_end = float(item.get("end", seg_start) or seg_start)
            except Exception:
                continue
            if min(end_sec, seg_end) <= max(start_sec, seg_start):
                continue
            speaker = self._normalize_runtime_speaker_id(item.get("speaker"))
            if not sequence or sequence[-1] != speaker:
                sequence.append(speaker)
        return sequence

    def _apply_inline_dialogue_speaker_split(
        self,
        row: dict,
        speaker_map: list[dict] | None = None,
    ) -> dict:
        explicit_speakers: list[str] = []
        seen_speakers: set[str] = set()
        for item in list(row.get("speaker_list") or []):
            speaker = self._normalize_runtime_speaker_id(item)
            if speaker and speaker not in seen_speakers:
                explicit_speakers.append(speaker)
                seen_speakers.add(speaker)
        mapped_speakers = self._speaker_sequence_for_range(row.get("start", 0.0), row.get("end", 0.0), speaker_map)
        turns = self._inline_dialogue_turns(
            row.get("text", ""),
            allow_missing_leading_marker=(
                len(explicit_speakers) >= 2
                or len(set(mapped_speakers)) >= 2
                or bool(row.get("_stt_speaker_marker_preserved"))
            ),
        )
        if len(turns) != 2:
            return row
        speakers = explicit_speakers[:2] or mapped_speakers
        if len(set(speakers)) < 2:
            try:
                from core.audio.diarize import get_speaker_for_segment

                start_sec = float(row.get("start", 0.0) or 0.0)
                end_sec = max(start_sec, float(row.get("end", start_sec) or start_sec))
                mid_sec = start_sec + ((end_sec - start_sec) / 2.0)
                first = self._normalize_runtime_speaker_id(get_speaker_for_segment(start_sec, mid_sec, speaker_map or []))
                second = self._normalize_runtime_speaker_id(get_speaker_for_segment(mid_sec, end_sec, speaker_map or []))
                if first != second:
                    speakers = [first, second]
            except Exception:
                pass
        if len(set(speakers)) < 2:
            speakers = list(self._dialogue_turn_speaker_pair())
        updated = dict(row)
        updated["speaker"] = speakers[0]
        updated["speaker_list"] = speakers[:2]
        updated["text"] = "\n".join(f"- {turn}" for turn in turns)
        updated["_speaker_dialogue_turn_split"] = {
            "task": "runtime_dialogue_turn_split",
            "turns": 2,
            "fallback_speakers": len(set(speakers[:2])) < 2,
        }
        return updated

    def _apply_runtime_speaker_diarization(
        self,
        segments: list[dict],
        *,
        merge_gap_sec: float = 1.5,
    ) -> list[dict]:
        rows = [dict(seg) for seg in list(segments or []) if isinstance(seg, dict)]
        speaker_map = list(getattr(self, "_speaker_map", []) or [])
        if not rows or not self._speaker_auto_processing_enabled():
            return rows

        get_speaker_for_segment = None
        if speaker_map:
            from core.audio.diarize import get_speaker_for_segment

        diarized_rows: list[dict] = []
        inline_split_count = 0
        for seg in rows:
            row = dict(seg)
            if callable(get_speaker_for_segment):
                row["speaker"] = self._normalize_runtime_speaker_id(
                    get_speaker_for_segment(row.get("start", 0.0), row.get("end", 0.0), speaker_map)
                )
            updated = self._apply_inline_dialogue_speaker_split(row, speaker_map)
            if updated.get("text") != row.get("text"):
                inline_split_count += 1
            diarized_rows.append(updated)

        grouped_rows: list[dict] = []
        for row in diarized_rows:
            speaker_list = [
                self._normalize_runtime_speaker_id(item)
                for item in list(row.get("speaker_list") or [])
                if self._normalize_runtime_speaker_id(item)
            ]
            if len(set(speaker_list)) >= 2:
                row["speaker_list"] = speaker_list[:2]
                row["speaker"] = speaker_list[0]
                grouped_rows.append(row)
                continue

            line_parts = [
                line.strip().lstrip("-").strip()
                for line in str(row.get("text", "") or "").splitlines()
                if line.strip()
            ]
            flat_text = " ".join(part for part in line_parts if part)
            if not flat_text:
                continue
            speaker = self._normalize_runtime_speaker_id(row.get("speaker"))
            if grouped_rows:
                prev = grouped_rows[-1]
                prev_speakers = [
                    self._normalize_runtime_speaker_id(item)
                    for item in list(prev.get("speaker_list") or [])
                    if self._normalize_runtime_speaker_id(item)
                ]
                gap = float(row.get("start", 0.0) or 0.0) - float(prev.get("end", 0.0) or 0.0)
                if (
                    gap < float(merge_gap_sec or 1.5)
                    and prev_speakers
                    and len(set(prev_speakers)) == 1
                    and speaker != prev_speakers[-1]
                    and len(prev_speakers) < 2
                ):
                    prev.setdefault("text_list", [str(prev.get("text", "") or "").strip()])
                    prev["text_list"].append(flat_text)
                    prev["speaker_list"] = prev_speakers + [speaker]
                    prev["end"] = max(float(prev.get("end", 0.0) or 0.0), float(row.get("end", 0.0) or 0.0))
                    continue

            grouped_rows.append(
                {
                    **row,
                    "speaker": speaker,
                    "speaker_list": [speaker],
                    "text_list": [flat_text],
                }
            )

        finalized_rows: list[dict] = []
        for row in grouped_rows:
            item = dict(row)
            text_list = [str(part).strip() for part in list(item.get("text_list") or []) if str(part).strip()]
            speaker_list = [
                self._normalize_runtime_speaker_id(part)
                for part in list(item.get("speaker_list") or [])
                if self._normalize_runtime_speaker_id(part)
            ]
            if text_list:
                if len(set(speaker_list)) >= 2 and len(text_list) >= 2:
                    item["text"] = "\n".join(f"- {part}" for part in text_list[:2])
                    item["speaker_list"] = speaker_list[:2]
                    item["speaker"] = item["speaker_list"][0]
                else:
                    item["text"] = text_list[0]
                    item["speaker_list"] = speaker_list[:1] or [self._normalize_runtime_speaker_id(item.get("speaker"))]
                    item["speaker"] = item["speaker_list"][0]
            item.pop("text_list", None)
            finalized_rows.append(item)

        if inline_split_count > 0:
            get_logger().log(f"🗣️ [화자 분리] 한 줄 대화 자막 {inline_split_count}개를 2줄 화자 자막으로 복원했습니다.")
        return finalized_rows

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

            project_path = str(getattr(getattr(self, "ui", None), "_current_project_path", "") or "")
            if project_path and os.path.exists(project_path):
                try:
                    from core.project.project_manager import save_project

                    save_project(
                        project_path,
                        segments=[],
                        stt_preview_segments=[],
                        provisional_cut_boundaries=[],
                        persist_analysis_artifacts=False,
                        recover_external_assets_on_empty=False,
                    )
                    get_logger().log("    └ 🧹 재시작용 프로젝트 자막 자산을 초기화했습니다.")
                except Exception as project_exc:
                    get_logger().log(f"    └ ⚠️ 프로젝트 자막 자산 초기화 실패: {project_exc}")

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
    def _emit_queue_status(self, queue_index, status, time_txt="", info_txt="", len_txt=""):
        ui = getattr(self, "ui", None)
        if ui is not None and hasattr(ui, "_sig_update_queue_payload"):
            try:
                ui._sig_update_queue_payload.emit(
                    build_queue_status_payload(queue_index, status, time_txt, info_txt, len_txt)
                )
                return
            except RuntimeError:
                pass

    def _emit_queue_header(self, current, total, pct, eta_str=""):
        ui = getattr(self, "ui", None)
        if ui is not None and hasattr(ui, "_sig_update_queue_header_payload"):
            try:
                ui._sig_update_queue_header_payload.emit(
                    build_queue_header_payload(current, total, pct, eta_str)
                )
                return
            except RuntimeError:
                pass

    def _save_project_for_queue_clip(self, target_file, srt_path, final_segments):
        from core.project.project_manager import create_project, save_project
        from core.work_mode import EDITOR_MODE

        ui = getattr(self, "ui", None)
        editor = getattr(ui, "_editor_widget", None) if ui is not None else None
        project_path = str(getattr(ui, "_current_project_path", "") or "") if ui is not None else ""
        settings = dict(getattr(editor, "settings", {}) or {})
        if not project_path:
            base_name = os.path.splitext(os.path.basename(target_file))[0]
            project_path = create_project(
                name=base_name,
                media_paths=[target_file],
                srt_path=srt_path,
                user_settings=settings,
            )
            if ui is not None:
                attach_project_session(
                    ui,
                    project_path,
                    None,
                    auto_pipeline=False,
                    clear_multiclip=False,
                    emit_boundary_signal=False,
                )

        workspace = {
            "last_playhead": 0.0,
            "last_cursor_block": 0,
            "active_clip_idx": 0,
            "active_work_mode": EDITOR_MODE,
        }
        try:
            if editor is not None and hasattr(editor, "video_player"):
                workspace["last_playhead"] = float(getattr(editor.video_player, "current_time", 0.0) or 0.0)
            if editor is not None and hasattr(editor, "text_edit"):
                workspace["last_cursor_block"] = int(editor.text_edit.textCursor().blockNumber())
        except Exception:
            pass

        stt_preview_segments = None
        voice_activity_segments = None
        provisional_cut_boundaries = None
        if editor is not None:
            aux_state = collect_editor_project_aux_state(editor)
            live_preview = aux_state["stt_preview_segments"]
            if live_preview:
                stt_preview_segments = live_preview
            voice_rows = aux_state["voice_activity_segments"]
            provisional_rows = aux_state["provisional_cut_boundaries"]
            if voice_rows:
                voice_activity_segments = voice_rows
            if provisional_rows:
                provisional_cut_boundaries = provisional_rows
            if provisional_cut_boundaries is None:
                auto_rows = list(getattr(editor, "_auto_cut_boundary_scan_lines", []) or [])
                if auto_rows:
                    provisional_cut_boundaries = auto_rows

        try:
            from core.project.recovery_state import build_recovery_checkpoint

            recovery_state = build_recovery_checkpoint(
                media_path=target_file,
                project_path=project_path,
                stage="complete",
                status="complete",
                detail="queue_clip_completed",
                segments=list(final_segments or []),
                artifacts={"srt_path": srt_path},
                settings=settings,
            )
        except Exception:
            recovery_state = None

        save_project(
            filepath=project_path,
            media_paths=[target_file],
            srt_path=srt_path,
            segments=list(final_segments or []),
            user_settings=settings,
            workspace=workspace,
            active_work_mode=EDITOR_MODE,
            voice_activity_segments=voice_activity_segments,
            stt_preview_segments=stt_preview_segments,
            provisional_cut_boundaries=provisional_cut_boundaries,
            recovery_state=recovery_state,
        )
        return project_path

    def _save_and_export(self, target_file, queue_index, final_segments, is_auto_mode):
        """SRT 저장 + MOV 렌더링 + 완료 처리"""
        get_logger().log("\n  [STEP 5] 💾 SRT 저장 중...")
        try:
            from core.engine.subtitle_engine import save_srt
            from core.path_manager import get_srt_path

            srt_path = get_srt_path(target_file)
            self._emit_queue_status(queue_index, "💾 SRT 저장 중", "", "", "")
            save_srt(final_segments, srt_path, apply_offset=True)
            get_logger().log(f"✅ {os.path.basename(srt_path)} 저장 완료")

            self._emit_queue_status(queue_index, "📦 프로젝트 저장 중", "", "", "")
            project_path = self._save_project_for_queue_clip(target_file, srt_path, final_segments)
            get_logger().log(f"📦 프로젝트 저장 완료: {os.path.basename(project_path)}")

            export_settings = {}
            try:
                from ui.dialogs.export_dialog import _load_es
                export_settings = _load_es()
            except Exception as exc:
                get_logger().log(f"⚠️ 자막영상 출력 설정 로드 실패, 기본값으로 렌더링합니다: {exc}")

            current_idx = queue_index + 1
            total_cnt = len(self.files_to_process)

            self._emit_queue_status(queue_index, "💾 SRT 저장됨", "", "", "")

            # ── STEP 6: MOV 렌더링 ──
            try:
                get_logger().log(
                    "\n  [STEP 6] 🎥 투명 자막 영상(MOV) 백그라운드 렌더링 중..."
                )
                self._emit_queue_status(queue_index, "🎥 자막영상출력(mov)", "", "", "")
                render_ok = self._run_background_render(
                    srt_path, target_file, export_settings, current_idx, total_cnt
                )
                if not render_ok:
                    self._emit_queue_status(queue_index, "❌ 자막영상출력 실패", "", "", "")
                    return False
            except Exception as e:
                get_logger().log(f"❌ MOV 렌더링 오류: {e}")
                get_logger().log(traceback.format_exc())
                self._emit_queue_status(queue_index, "❌ 자막영상출력 실패", "", "", "")
                return False

            try:
                from core.auto_tracker import AutoTracker

                AutoTracker().mark_completed(target_file)
                if hasattr(self.ui, "mark_cloud_file_done"):
                    self.ui.mark_cloud_file_done(target_file)
            except Exception:
                pass

            self._emit_queue_status(
                queue_index,
                "✅ 완료" if is_auto_mode else "✅ 자막생성완료",
                "",
                "",
                "",
            )
            return True

        except Exception as e:
            get_logger().log(f"❌ 처리 실패: {e}")
            self._emit_queue_status(queue_index, "❌ 저장 실패", "", "", "")
            return False

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
        self._speaker_auto_enabled = speaker_diarization_auto_enabled(s)
        self._effective_min_speakers = self.min_speakers
        self._effective_max_speakers = self.max_speakers

    def _load_selected_model(self):
        s = load_settings()
        return s.get("selected_model", getattr(config, "OLLAMA_MODEL", "exaone3.5:7.8b"))

    def _prepare_speaker_map(self, audio_path):
        try:
            from core.audio.diarize import get_speaker_map

            min_speakers, max_speakers = self._runtime_speaker_limits()
            self._speaker_map = get_speaker_map(
                audio_path, min_speakers, max_speakers
            )
        except Exception:
            self._speaker_map = []

    def _speaker_diarization_audio_path(self, target_file: str, chunk_dir: str | None = None) -> str:
        audio_for_diarization = str(target_file or "")
        base_name = os.path.splitext(os.path.basename(str(target_file or "")))[0]
        cleaned_wav = str(getattr(self.video_processor, "last_cleaned_wav", "") or "")
        raw_wav = str(getattr(self.video_processor, "last_raw_wav", "") or "")
        if (not cleaned_wav or not os.path.exists(cleaned_wav) or not raw_wav or not os.path.exists(raw_wav)) and hasattr(self.video_processor, "_audio_work_paths"):
            try:
                audio_paths = self.video_processor._audio_work_paths(target_file)
                cleaned_wav = str(audio_paths.get("cleaned_wav") or cleaned_wav)
                raw_wav = str(audio_paths.get("raw_wav") or raw_wav)
            except Exception:
                pass
        if not cleaned_wav:
            cleaned_wav = os.path.join(config.OUTPUT_DIR, f"{base_name}_cleaned.wav")
        if not raw_wav:
            raw_wav = os.path.join(config.OUTPUT_DIR, f"{base_name}.wav")
        if os.path.exists(cleaned_wav):
            return cleaned_wav
        if os.path.exists(raw_wav):
            return raw_wav

        if target_file and raw_wav:
            try:
                os.makedirs(os.path.dirname(raw_wav), exist_ok=True)
                extract_cmd = [
                    ffmpeg_binary(),
                    "-y",
                    "-nostdin",
                    "-loglevel",
                    "error",
                    "-i",
                    target_file,
                    *self.video_processor._ffmpeg_audio_stream_args(),
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-acodec",
                    "pcm_s16le",
                    raw_wav,
                ]
                runner = getattr(self.video_processor, "_run_media_command", None)
                if callable(runner) and runner(extract_cmd, label="화자 분리용 전체 오디오 추출"):
                    return raw_wav
            except Exception as exc:
                get_logger().log(f"⚠️ [화자 분리] 전체 오디오 추출 실패: {exc}")

        if chunk_dir:
            try:
                wav_in_chunks = sorted(
                    os.path.join(chunk_dir, name)
                    for name in os.listdir(chunk_dir)
                    if str(name).lower().endswith(".wav")
                )
                if wav_in_chunks:
                    audio_for_diarization = wav_in_chunks[0]
            except Exception:
                pass
        return audio_for_diarization

    # ─── NTFY 알림 ───────────────────────────────────────
    def _send_ntfy_notification(self, title, message, tags=""):
        from core.notifier import send_ntfy

        send_ntfy(title, message, tags)

    # ─── 프리페치 ────────────────────────────────────────
    def _validate_audio_extract_result(self, result, target_file=None, *, context: str = "오디오 추출"):
        """Return a usable audio extraction result only when STT wav chunks exist."""
        if not result:
            return None
        try:
            chunk_dir = result[0]
        except Exception:
            chunk_dir = ""
        try:
            has_chunks = os.path.isdir(chunk_dir) and any(
                str(name).lower().endswith(".wav") for name in os.listdir(chunk_dir)
            )
        except Exception:
            has_chunks = False
        if has_chunks:
            return result

        label = os.path.basename(str(target_file or "")) if target_file else ""
        suffix = f" ({label})" if label else ""
        get_logger().log(f"❌ {context} 실패: 생성된 STT 청크가 없습니다{suffix}")
        return None

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
                tune = self._auto_audio_tune_settings_for_file(target_file)
                if hasattr(vp, "set_auto_audio_tune_overrides"):
                    vp.set_auto_audio_tune_overrides(tune)
                vp.extract_audio(target_file, prefetch_only=True)
                with self._prefetch_lock:
                    if current_generation == self._prefetch_generation:
                        self._prefetch_cache[target_file] = None
            except Exception as e:
                get_logger().log(
                    f"⚠️ 오디오 선추출 실패: {os.path.basename(target_file)} / {e}"
                )
                with self._prefetch_lock:
                    if current_generation == self._prefetch_generation:
                        self._prefetch_cache[target_file] = None
            finally:
                try:
                    if hasattr(vp, "release_runtime_models"):
                        vp.release_runtime_models()
                    else:
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

        tune = self._auto_audio_tune_settings_for_file(target_file)
        if hasattr(self.video_processor, "set_auto_audio_tune_overrides"):
            self.video_processor.set_auto_audio_tune_overrides(tune)
        self._publish_auto_audio_tune_for_sidebar(target_file, tune)
        if cached:
            return self._validate_audio_extract_result(cached, target_file)
        return self._validate_audio_extract_result(
            self.video_processor.extract_audio(target_file),
            target_file,
        )

    def _publish_auto_audio_tune_for_sidebar(self, target_file: str, tune: dict | None, *, decision: dict | None = None) -> None:
        ui = getattr(self, "ui", None)
        if ui is None:
            return
        payload = {"tune": dict(tune or {}), "decision": dict(decision or {})}
        signal = getattr(ui, "_sig_runtime_audio_tune", None)
        if signal is not None and hasattr(signal, "emit"):
            try:
                signal.emit(str(target_file or ""), payload)
                return
            except Exception:
                pass
        setter = getattr(ui, "_set_runtime_audio_tune_display", None)
        if callable(setter):
            try:
                setter(str(target_file or ""), payload)
            except Exception:
                pass

    def _auto_audio_tune_enabled(self) -> bool:
        try:
            settings = load_settings()
            if bool(settings.get("audio_preset_auto_benchmark_locked", False)):
                return False
            return not bool(settings.get("audio_preset_auto_disabled", False))
        except Exception:
            return True

    def _auto_audio_tune_settings_for_file(self, target_file: str) -> dict:
        if not self._auto_audio_tune_enabled():
            return {}
        target_file = str(target_file or "")
        if not target_file:
            return {}
        cache = getattr(self, "_auto_audio_tune_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._auto_audio_tune_cache = cache
        if target_file in cache:
            return dict(cache.get(target_file) or {})
        try:
            from core.audio.preset_auto_classifier import (
                append_audio_lora_record,
                apply_auto_classified_presets,
                auto_classify_media_presets,
                format_auto_audio_decision_log,
            )

            base_settings = dict(load_settings())
            decision = auto_classify_media_presets(target_file, settings=base_settings)
            updated = apply_auto_classified_presets(base_settings, decision)
            tune = dict(updated.get("audio_preset_auto_tune") or {})
            cache[target_file] = tune
            try:
                append_audio_lora_record(decision, target_file)
            except Exception as record_exc:
                get_logger().log(f"  ⚠️ [오토 오디오] LoRA 누적 기록 실패: {record_exc}")
            get_logger().log(format_auto_audio_decision_log(decision, target_file))
            return tune
        except Exception as exc:
            get_logger().log(f"⚠️ 오디오 자동 튜닝 실패: {os.path.basename(target_file)} / {exc}")
            cache[target_file] = {}
            return {}

from core.pipeline.topicless_segments import install_topicless_segment_helpers  # noqa: E402

install_topicless_segment_helpers(PipelineHelpersMixin)
