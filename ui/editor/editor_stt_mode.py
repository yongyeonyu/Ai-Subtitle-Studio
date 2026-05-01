# Version: 03.02.06
# Phase: PHASE1-D
"""
Editor STT follow-along mode.
"""
import threading

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QMessageBox

from logger import get_logger
from ui.editor.subtitle_text_edit import SubtitleBlockData


class EditorSTTModeMixin:
    def _init_stt_mode_state(self):
        self._stt_mode_enabled = False
        self._stt_recording = False
        self._stt_vad_running = False
        self._stt_repeat_timer = QTimer(self)
        self._stt_repeat_timer.setSingleShot(True)
        self._stt_repeat_timer.timeout.connect(self._finish_stt_repeat_segment)

    def _toggle_stt_mode(self):
        if getattr(self, "_stt_mode_enabled", False):
            self._set_stt_mode_enabled(False)
            return
        if getattr(self, "_is_ai_processing", False):
            reply = QMessageBox.question(
                self,
                "STT 모드",
                "STT모드를 시작하시겠습니까?\n현재 진행 중인 자막 생성 작업은 취소됩니다.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            try:
                if hasattr(self, "_stop_pipeline"):
                    self._stop_pipeline()
            except Exception as exc:
                get_logger().log(f"⚠️ STT 전환 중 기존 작업 취소 실패: {exc}")
            self._set_stt_mode_enabled(True)
            QTimer.singleShot(300, self._start_stt_vad_detection)
            return
        self._set_stt_mode_enabled(True)

    def _set_stt_mode_enabled(self, enabled: bool):
        self._stt_mode_enabled = bool(enabled)
        if enabled:
            self.status_lbl.setText("🎙️ STT 모드 ON")
            get_logger().log("🎙️ STT 모드 ON: 시작 버튼을 누르면 VAD-only STT 세그먼트를 생성합니다.")
        else:
            self._stt_recording = False
            self._stt_vad_running = False
            self.status_lbl.setText("✏️ STT 모드 OFF")
            get_logger().log("🎙️ STT 모드 OFF")
        self._refresh_stt_visuals()

    def _start_stt_vad_detection(self) -> bool:
        if not getattr(self, "_stt_mode_enabled", False):
            return False
        if getattr(self, "_stt_vad_running", False):
            get_logger().log("🎙️ STT VAD 생성이 이미 진행 중입니다.")
            return True
        media_path = getattr(self, "media_path", "") or getattr(self.sm, "current_file", "")
        if not media_path:
            self.status_lbl.setText("⚠️ STT VAD: 파일 없음")
            get_logger().log("⚠️ STT 모드: VAD를 실행할 미디어 파일이 없습니다.")
            return True

        self._stt_vad_running = True
        self.status_lbl.setText("🎙️ STT VAD 생성 중...")
        get_logger().log("🎙️ STT 모드 시작: 최고 민감도 VAD로 음성 구간만 탐지합니다.")

        def _worker():
            segs = []
            try:
                from core.audio.stt_vad import detect_stt_speech_segments

                segs = detect_stt_speech_segments(media_path)
            except Exception as exc:
                get_logger().log(f"⚠️ STT VAD 생성 실패: {exc}")
            finally:
                self.sig_stt_vad_segments.emit(segs)

        threading.Thread(target=_worker, daemon=True, name="editor-stt-vad-mode").start()
        return True

    def _apply_stt_vad_segments(self, vad_segs: list[dict]):
        self._stt_vad_running = False
        if not getattr(self, "_stt_mode_enabled", False):
            return
        if not vad_segs:
            self.status_lbl.setText("⚠️ STT 음성 구간 없음")
            return
        self._create_stt_segments_from_vad(vad_segs)
        try:
            self.timeline.set_vad_segments(vad_segs)
        except Exception:
            pass
        self._mark_dirty()
        self.status_lbl.setText(f"🎙️ STT 세그먼트 {len(vad_segs)}개")
        self._refresh_stt_visuals()
        try:
            self._auto_save_project(self._get_current_segments())
        except Exception as exc:
            get_logger().log(f"⚠️ STT 프로젝트 저장 실패: {exc}")
        get_logger().log(f"🎙️ STT 세그먼트 생성 완료: {len(vad_segs)}개 (SRT 저장 제외, 프로젝트 저장 대상)")

    def _ensure_stt_segments(self) -> int:
        if getattr(self, "_segment_queue", None):
            try:
                self._flush_queue()
            except Exception:
                pass
        segs = [s for s in self._get_current_segments() if not s.get("is_gap")]
        if not segs:
            vad_segs = []
            try:
                vad_segs = list(getattr(self.timeline.canvas, "vad_segments", []) or [])
            except Exception:
                vad_segs = []
            if vad_segs:
                self._create_stt_segments_from_vad(vad_segs)
                segs = [s for s in self._get_current_segments() if not s.get("is_gap")]

        changed = 0
        doc = self.text_edit.document()
        block = doc.begin()
        while block.isValid():
            ud = block.userData()
            text = block.text().strip()
            if isinstance(ud, SubtitleBlockData) and not ud.is_gap:
                ud.stt_mode = True
                if not getattr(ud, "dictated_text", ""):
                    ud.stt_pending = True
                    ud.original_text = getattr(ud, "original_text", "") or text
                    changed += 1
            block = block.next()
        return changed

    def _create_stt_segments_from_vad(self, vad_segs: list[dict]):
        doc = self.text_edit.document()
        cur = QTextCursor(doc)
        cur.beginEditBlock()
        cur.select(QTextCursor.SelectionType.Document)
        cur.removeSelectedText()
        for idx, vad in enumerate(vad_segs):
            if idx > 0:
                cur.insertText("\n")
            start = round(float(vad.get("start", 0.0) or 0.0), 2)
            end = round(float(vad.get("end", start + 0.3) or start + 0.3), 2)
            data = SubtitleBlockData(
                "00",
                start,
                stt_mode=True,
                stt_pending=True,
                original_text="",
            )
            data.end_sec = max(start + 0.1, end)
            cur.block().setUserData(data)
        if vad_segs:
            end = round(float(vad_segs[-1].get("end", vad_segs[-1].get("start", 0.0)) or 0.0), 2)
            cur.insertText("\n")
            cur.block().setUserData(SubtitleBlockData("00", end, is_gap=True))
        cur.endEditBlock()
        self.text_edit.update_margins()

    def _refresh_stt_visuals(self):
        try:
            self._highlighter.rehighlight()
        except Exception:
            pass
        self._schedule_timeline()
        if hasattr(self, "global_menu_bar"):
            self.global_menu_bar.refresh()
        main_w = self.window()
        if hasattr(main_w, "global_menu_bar"):
            main_w.global_menu_bar.refresh()

    def _current_stt_block(self):
        block = self.text_edit.textCursor().block()
        if block.isValid():
            ud = block.userData()
            if isinstance(ud, SubtitleBlockData) and not ud.is_gap:
                return block
        doc = self.text_edit.document()
        block = doc.begin()
        while block.isValid():
            ud = block.userData()
            if isinstance(ud, SubtitleBlockData) and not ud.is_gap and getattr(ud, "stt_pending", False):
                return block
            block = block.next()
        return self.text_edit.textCursor().block()

    def _handle_stt_enter(self):
        if not getattr(self, "_stt_mode_enabled", False):
            return
        if self._stt_recording:
            self.status_lbl.setText("🎙️ 녹음 종료 대기...")
            return
        block = self._current_stt_block()
        if not block.isValid():
            return
        self._stt_recording = True
        self._stt_target_line = block.blockNumber()
        self.status_lbl.setText("🎙️ 녹음 중...")
        if hasattr(self, "timeline") and hasattr(self.timeline, "canvas"):
            self.timeline.canvas._is_listening = True
            self.timeline.canvas.update()
        get_logger().log("🎙️ STT 따라말하기 녹음 시작")

        def _worker():
            text = ""
            try:
                from core.audio.live_stt import transcribe_microphone_once

                result = transcribe_microphone_once("quality")
                text = result.text
                if text:
                    get_logger().log(
                        f"🎙️ STT 따라말하기 완료: {result.engine} / {result.model} / {result.elapsed:.1f}s"
                    )
            except Exception as exc:
                get_logger().log(f"⚠️ STT 따라말하기 실패: {exc}")
            finally:
                self.sig_live_stt_result.emit(text)

        threading.Thread(target=_worker, daemon=True, name="editor-stt-follow-mode").start()

    def _apply_stt_text_to_current(self, text: str):
        self._stt_recording = False
        if hasattr(self, "timeline") and hasattr(self.timeline, "canvas"):
            self.timeline.canvas._is_listening = False
            self.timeline.canvas.update()
        text = str(text or "").strip()
        if not text:
            self.status_lbl.setText("🎙️ STT 결과 없음")
            return
        if hasattr(self, "_stt_target_line"):
            line = int(getattr(self, "_stt_target_line", 0) or 0)
            block = self.text_edit.document().findBlockByNumber(line)
            if not block.isValid():
                block = self._current_stt_block()
        else:
            block = self._current_stt_block()
        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData):
            return
        ud.stt_mode = True
        ud.stt_pending = False
        ud.dictated_text = text

        cur = QTextCursor(self.text_edit.document())
        cur.beginEditBlock()
        cur.setPosition(block.position())
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cur.removeSelectedText()
        cur.insertText(text)
        cur.block().setUserData(ud)
        cur.endEditBlock()
        self.text_edit.setTextCursor(cur)
        self._mark_dirty()
        self.status_lbl.setText("✅ STT 적용 완료")
        self._refresh_stt_visuals()
        self._refresh_video_subtitle_context()

    def _handle_stt_space(self):
        if not getattr(self, "_stt_mode_enabled", False):
            return
        block = self._current_stt_block()
        if not block.isValid():
            return
        self._select_block(block)
        ud = block.userData()
        start = float(getattr(ud, "start_sec", 0.0) or 0.0)
        end = self._stt_block_end(block, start)
        self._play_stt_repeat_segment(start, end)

    def _select_block(self, block):
        cur = QTextCursor(block)
        self.text_edit.setTextCursor(cur)
        self._active_seg_start = float(getattr(block.userData(), "start_sec", 0.0) or 0.0)
        try:
            self.timeline.set_active(self._active_seg_start)
            self.timeline.set_playhead(self._active_seg_start)
            self.timeline.center_to_sec(self._active_seg_start, smooth=True)
        except Exception:
            pass

    def _stt_block_end(self, block, start: float) -> float:
        b = block.next()
        while b.isValid():
            ud = b.userData()
            if isinstance(ud, SubtitleBlockData) and not ud.is_gap:
                return max(start + 0.2, float(ud.start_sec))
            b = b.next()
        total = float(getattr(getattr(self, "video_player", None), "total_time", 0.0) or 0.0)
        return total if total > start else start + 3.0

    def _play_stt_repeat_segment(self, start: float, end: float):
        if not hasattr(self, "video_player"):
            return
        self._stt_repeat_start = start
        self.video_player.pause_video()
        self.video_player.seek(start)
        self.video_player.toggle_play()
        ms = max(200, int((end - start) * 1000))
        self._stt_repeat_timer.start(ms)

    def _finish_stt_repeat_segment(self):
        if hasattr(self, "video_player"):
            self.video_player.pause_video()
            self.video_player.seek(float(getattr(self, "_stt_repeat_start", 0.0) or 0.0))

    def _warn_pending_stt_before_save(self, segs: list[dict]) -> bool:
        pending = [s for s in segs if s.get("stt_pending")]
        if not pending:
            return True
        reply = QMessageBox.warning(
            self,
            "STT 미완료 세그먼트",
            f"완료 전 STT 세그먼트 {len(pending)}개는 SRT에 저장되지 않습니다.\n계속 저장할까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes
