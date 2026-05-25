# Version: 03.14.31
# Phase: PHASE2
"""Subtitle quality review actions for EditorWidget."""
import time

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QMessageBox

from core.runtime.logger import get_logger
from ui.editor.ux.subtitle_text_edit import SubtitleBlockData


class EditorQualityReviewMixin:
    def _quality_vad_segments(self) -> list[dict]:
        try:
            return list(getattr(self.timeline.canvas, "vad_segments", []) or [])
        except Exception:
            return []

    def _set_quality_running(self, running: bool):
        self._quality_review_running = bool(running)
        if hasattr(self, "btn_quality_review"):
            self.btn_quality_review.setEnabled(not running)
            self.btn_quality_review.setText("검사 중" if running else "검사")
        if hasattr(self, "status_lbl"):
            self.status_lbl.setText("에디터 | 검사 중" if running else "에디터 | 검사 완료")

    def _is_video_playback_active(self) -> bool:
        try:
            player = getattr(getattr(self, "video_player", None), "media_player", None)
            return bool(player and player.playbackState() == player.PlaybackState.PlayingState)
        except Exception:
            return False

    def _schedule_auto_quality_review(self, delay_ms: int = 900) -> None:
        self._auto_quality_review_pending = True
        if bool(getattr(self, "_auto_quality_review_scheduled", False)):
            return
        self._auto_quality_review_scheduled = True
        QTimer.singleShot(max(0, int(delay_ms)), self._run_scheduled_auto_quality_review)

    def _run_scheduled_auto_quality_review(self) -> None:
        self._auto_quality_review_scheduled = False
        if not bool(getattr(self, "_auto_quality_review_pending", False)):
            return
        try:
            locked = bool(getattr(getattr(self, "sm", None), "is_locked", False))
        except Exception:
            locked = False
        try:
            recent_activity_at = float(getattr(self, "_last_editor_foreground_activity_at", 0.0) or 0.0)
            defer_after_edit_sec = float(self.settings.get("subtitle_quality_defer_after_edit_sec", 4.0) or 4.0)
            recent_editor_activity = recent_activity_at > 0.0 and (time.monotonic() - recent_activity_at) < max(0.25, defer_after_edit_sec)
        except Exception:
            recent_editor_activity = False
        playback_active = self._is_video_playback_active()
        if locked or playback_active or recent_editor_activity:
            if playback_active and not bool(getattr(self, "_auto_quality_review_defer_logged", False)):
                self._auto_quality_review_defer_logged = True
                get_logger().log("[자막 품질] 재생 중이라 자동 품질 검사를 잠시 미룹니다.")
            self._auto_quality_review_scheduled = True
            delay_ms = 1800 if playback_active else 1200 if recent_editor_activity else 700
            QTimer.singleShot(delay_ms, self._run_scheduled_auto_quality_review)
            return
        self._auto_quality_review_pending = False
        self._auto_quality_review_defer_logged = False
        self._run_quality_review(auto_correct=bool(self.settings.get("subtitle_quality_auto_correct_enabled", False)))

    def _run_quality_review(self, auto_correct: bool | None = None):
        from core.subtitle_quality.quality_pipeline import run_subtitle_quality_pipeline

        auto_checkbox = getattr(self, "chk_quality_auto", None)
        auto = bool(auto_checkbox.isChecked()) if auto_correct is None and auto_checkbox is not None else bool(auto_correct)
        if auto:
            self.settings["subtitle_quality_auto_correct_enabled"] = True
        self.settings["subtitle_quality_enabled"] = True
        segs = [seg for seg in self._get_current_segments() if not seg.get("is_gap")]
        if not segs:
            QMessageBox.information(self, "품질 검사", "검사할 자막이 없습니다.")
            return
        self._set_quality_running(True)
        try:
            result = run_subtitle_quality_pipeline(
                segs,
                vad_segments=self._quality_vad_segments(),
                settings=self.settings,
                auto_correct=auto,
                context={
                    "clip_boundaries": list(getattr(self.timeline.canvas, "_multiclip_boxes", []) or []),
                },
            )
            self._apply_quality_result(result, auto_correct=auto)
            summary = result.summary
            score = "-" if summary.overall_score is None else f"{summary.overall_score:.1f}"
            get_logger().log(
                f"[자막 품질] 검사 완료: 전체 {score}점, 확인 필요 {summary.needs_review_count}개, 자동 교정 {summary.auto_corrected_count}개"
            )
        except Exception as exc:
            get_logger().log(f"⚠️ 자막 품질 검사 오류: {exc}")
            QMessageBox.warning(self, "품질 검사 오류", str(exc))
        finally:
            self._set_quality_running(False)
            self._auto_quality_review_pending = False
            self._auto_quality_review_defer_logged = False
            try:
                restorer = getattr(self.window(), "_restore_normal_cursor", None)
                if callable(restorer):
                    restorer(self)
            except Exception:
                pass
            try:
                if bool(getattr(self, "_generation_completion_autosave_pending", False)):
                    scheduler = getattr(self, "_schedule_generation_completion_autosave", None)
                    if callable(scheduler):
                        scheduler(delay_ms=0)
            except Exception:
                pass

    def _apply_quality_result(self, result, *, auto_correct: bool = False):
        self._quality_summary = getattr(result, "summary", None)
        result_by_line = {}
        for idx, seg in enumerate(getattr(result, "segments", []) or []):
            line = int(seg.get("line", idx) if seg.get("line") is not None else idx)
            result_by_line[line] = dict(seg)

        if auto_correct and hasattr(self, "_undo_mgr"):
            self._undo_mgr.push_immediate()

        doc = self.text_edit.document()
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        quality_map: dict[int, dict] = {}
        for line, seg in result_by_line.items():
            block = doc.findBlockByNumber(int(line))
            if not block.isValid():
                continue
            data = block.userData()
            if not isinstance(data, SubtitleBlockData) or data.is_gap:
                continue
            new_text = str(seg.get("text", "") or "")
            if auto_correct and new_text and new_text != block.text():
                cursor.setPosition(block.position())
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                cursor.insertText(new_text)
                block = cursor.block()
            quality = dict(seg.get("quality") or {})
            quality_map[int(line)] = quality
            seg_for_sig = {
                "start": data.start_sec,
                "end": seg.get("end", data.start_sec),
                "text": block.text(),
                "speaker": data.spk_id,
            }
            block.setUserData(
                SubtitleBlockData(
                    data.spk_id,
                    data.start_sec,
                    data.is_gap,
                    stt_mode=getattr(data, "stt_mode", False),
                    stt_pending=getattr(data, "stt_pending", False),
                    original_text=getattr(data, "original_text", ""),
                    dictated_text=getattr(data, "dictated_text", ""),
                    quality=quality,
                    quality_history=list(seg.get("quality_history") or []),
                    quality_candidates=list(seg.get("quality_candidates") or []),
                    quality_signature=self._segment_quality_signature(seg_for_sig),
                )
            )
        cursor.endEditBlock()

        if hasattr(self, "_highlighter"):
            self._highlighter.set_quality_map(quality_map)
            self._highlighter.set_quality_filter(self._quality_filter_key)
        self._update_quality_summary_label()
        self._schedule_timeline()
        self._refresh_video_subtitle_context()
        if auto_correct:
            self._mark_dirty()

    def _update_quality_summary_label(self):
        summary = self._quality_summary
        if not hasattr(self, "quality_summary_lbl"):
            return
        if summary is None:
            self.quality_summary_lbl.setText("품질 미검사")
            return
        score = "-" if summary.overall_score is None else f"{summary.overall_score:.1f}"
        before_after = ""
        if summary.before_score is not None and summary.after_score is not None and summary.before_score != summary.after_score:
            delta = summary.after_score - summary.before_score
            before_after = f" · {summary.before_score:.1f}→{summary.after_score:.1f} ({delta:+.1f})"
        self.quality_summary_lbl.setText(
            f"품질 {score}점{before_after} · 확인 {summary.needs_review_count} · 교정 {summary.auto_corrected_count}"
        )

    def _on_quality_filter_changed(self, *_args):
        combo = getattr(self, "quality_filter_combo", None)
        self._quality_filter_key = str(combo.currentData() if combo else "all") or "all"
        if hasattr(self, "_highlighter"):
            self._highlighter.set_quality_filter(self._quality_filter_key)
        if hasattr(self, "timeline") and hasattr(self.timeline, "canvas"):
            self.timeline.canvas.quality_filter = self._quality_filter_key
            self.timeline.canvas.update()

    def _segment_for_line(self, line: int) -> dict | None:
        for seg in self._get_current_segments():
            if int(seg.get("line", -1) or -1) == int(line):
                return seg
        return None

    def _show_quality_candidates_for_current_line(self):
        from ui.editor.quality_candidate_dialog import QualityCandidateDialog

        line = self.text_edit.textCursor().blockNumber()
        seg = self._segment_for_line(line)
        if not seg or not seg.get("quality"):
            QMessageBox.information(self, "후보 비교", "현재 줄에 품질 검사 결과가 없습니다.")
            return
        dialog = QualityCandidateDialog(seg, self)
        if dialog.exec() != 1 or not dialog.selected_candidate:
            return
        candidate = dict(dialog.selected_candidate)
        text = str(candidate.get("text", "") or "")
        if not text:
            return
        old_seg = self._segment_for_line(line) or {}
        self._replace_segment_text_by_line(line, text, candidate)
        try:
            from core.subtitle_quality.correction_memory import add_correction_memory_item
            add_correction_memory_item(
                str(old_seg.get("text", "") or ""),
                text,
                source="quality_candidate",
                context=str(candidate.get("reason", "") or ""),
            )
        except Exception:
            pass

    def _show_subtitle_why_for_current_line(self):
        from ui.editor.subtitle_why_dialog import SubtitleWhyDialog

        line = self.text_edit.textCursor().blockNumber()
        seg = self._segment_for_line(line)
        if not seg:
            QMessageBox.information(self, "생성 근거", "현재 줄에서 확인할 자막을 찾지 못했습니다.")
            return
        dialog = SubtitleWhyDialog(seg, index=line, parent=self)
        if dialog.exec() == 1 and getattr(dialog, "selected_action", ""):
            self._handle_one_click_fix_action(line, str(dialog.selected_action))

    def _handle_one_click_fix_action(self, line: int, action: str):
        from core.engine.subtitle_one_click_fix import (
            build_one_click_fix_request,
            reapply_similar_subtitle_style,
            subtitle_source_text_without_llm,
        )

        seg = self._segment_for_line(int(line)) or {}
        if not seg:
            return
        if action == "restore_source_no_llm":
            restored = subtitle_source_text_without_llm(seg)
            if not restored:
                QMessageBox.information(self, "원문 복구", "복구할 원문/STT 후보가 없습니다.")
                return
            self._replace_segment_text_by_line(
                int(line),
                restored,
                {"candidate_id": action, "source": "one_click_fix", "reason": "LLM 없이 원문 기준 복구"},
            )
            return
        if action == "reapply_similar_style":
            updated, meta = reapply_similar_subtitle_style(str(seg.get("text", "") or ""), getattr(self, "settings", {}) or {})
            if not updated or updated == str(seg.get("text", "") or ""):
                QMessageBox.information(self, "스타일 재적용", str(meta.get("reason") or "적용할 유사 스타일을 찾지 못했습니다."))
                return
            self._replace_segment_text_by_line(
                int(line),
                updated,
                {"candidate_id": action, "source": "one_click_fix", "reason": str(meta.get("reason") or "비슷한 자막 스타일 재적용")},
            )
            return
        request = build_one_click_fix_request(action, seg, reason="one_click_fix")
        if action == "re_recognize_region" and hasattr(self, "_re_recognize_segment"):
            self._re_recognize_segment(float(seg.get("start", 0.0) or 0.0))
            return
        if action == "recheck_cut_only":
            try:
                if hasattr(self, "video_player") and hasattr(self.video_player, "seek"):
                    self.video_player.seek(float(seg.get("start", 0.0) or 0.0))
                if hasattr(self, "_on_scan_cut_requested"):
                    self._on_scan_cut_requested(1)
                    return
            except Exception:
                pass
        self._mark_one_click_fix_request(int(line), request)
        QMessageBox.information(self, "빠른 수정", f"{request.get('label')} 요청을 현재 자막에 표시했습니다.")

    def _mark_one_click_fix_request(self, line: int, request: dict):
        for seg in list(getattr(self, "_cached_segs", []) or []):
            if int(seg.get("line", -1) or -1) == int(line):
                seg["_one_click_fix_request"] = dict(request)
                quality = dict(seg.get("quality") or {})
                flags = list(quality.get("flags") or [])
                if "one_click_fix_requested" not in flags:
                    flags.append("one_click_fix_requested")
                quality["flags"] = flags
                quality["one_click_fix_request"] = dict(request)
                seg["quality"] = quality
                break
        self._mark_dirty()

    def _replace_segment_text_by_line(self, line: int, text: str, candidate: dict | None = None):
        block = self.text_edit.document().findBlockByNumber(int(line))
        if not block.isValid():
            return
        data = block.userData()
        if not isinstance(data, SubtitleBlockData) or data.is_gap:
            return
        current_seg = self._segment_for_line(line) or {}
        if hasattr(self, "_undo_mgr"):
            self._undo_mgr.push_immediate()
        cur = QTextCursor(block)
        cur.beginEditBlock()
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cur.insertText(text)
        quality = dict(getattr(data, "quality", {}) or {})
        previous_quality = dict(quality)
        flags = list(quality.get("flags") or [])
        if "candidate_applied" not in flags:
            flags.append("candidate_applied")
        quality["flags"] = flags
        quality["candidate_applied_reason"] = str((candidate or {}).get("reason", "") or "")
        quality, quality_changed = self._manual_confirmed_quality_for_user_edit(
            quality,
            reason="manual_text_edit",
        )
        history = list(getattr(data, "quality_history", []) or [])
        if quality_changed and previous_quality and previous_quality != quality:
            history.append(dict(previous_quality))
        cur.block().setUserData(
            SubtitleBlockData(
                data.spk_id,
                data.start_sec,
                data.is_gap,
                stt_mode=getattr(data, "stt_mode", False),
                stt_pending=getattr(data, "stt_pending", False),
                original_text=getattr(data, "original_text", ""),
                dictated_text=getattr(data, "dictated_text", ""),
                quality=quality,
                quality_history=history,
                quality_candidates=list(getattr(data, "quality_candidates", []) or []),
                quality_signature=self._segment_quality_signature({
                    "start": data.start_sec,
                    "end": current_seg.get("end", data.start_sec),
                    "text": text,
                    "speaker": data.spk_id,
                }),
            )
        )
        cur.endEditBlock()
        self._mark_dirty()
        self._finalize_edit()
