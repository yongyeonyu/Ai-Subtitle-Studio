# Version: 03.02.06
# Phase: PHASE1-D
"""
Editor STT follow-along mode.
"""
import os
import threading

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QMessageBox

from core.runtime.logger import get_logger
from ui.editor.subtitle_text_edit import SubtitleBlockData


class EditorSTTModeMixin:
    def _init_stt_mode_state(self):
        self._stt_mode_enabled = False
        self._stt_state = "disabled"
        self._stt_state_detail = {}
        self._stt_recording = False
        self._stt_vad_running = False
        self._stt_mic_capture_session = None
        self._stt_work_segments = []
        self._stt_raw_dictation_segments = []
        self._stt_final_segments = []
        self._stt_rolling_windows = []
        self._stt_learning_events = []
        self._stt_adapter_refs = {}
        self._stt_lora_bundle_info = {}
        self._stt_replay_counts = {}
        self._stt_repeat_timer = QTimer(self)
        self._stt_repeat_timer.setSingleShot(True)
        self._stt_repeat_timer.timeout.connect(self._finish_stt_repeat_segment)

    def _stt_set_state(self, state: str, detail: dict | None = None) -> None:
        self._stt_state = str(state or "disabled")
        self._stt_state_detail = dict(detail or {})
        try:
            progress = self._stt_progress_summary()
            suffix = f" · {progress}" if progress else ""
            self.status_lbl.setText(f"🎙️ STT: {self._stt_state}{suffix}")
        except Exception:
            pass

    def _stt_progress_summary(self) -> str:
        work = list(getattr(self, "_stt_work_segments", []) or [])
        total = len(work)
        if total <= 0:
            return ""
        completed = sum(1 for row in work if not row.get("stt_pending") or row.get("stt_mode_status") in {"input_done", "resegmented"})
        current = getattr(self, "_stt_target_line", None)
        return f"{completed}/{total} 완료" + (f" · line {current + 1}" if current is not None else "")

    def _stt_input_provider(self) -> str:
        settings = dict(getattr(self, "settings", {}) or {})
        provider = str(settings.get("stt_mode_text_input_provider") or "manual").strip().lower()
        if provider in {"os", "os_dictation", "dictation"}:
            return "os_dictation"
        if provider in {"mic", "desktop_mic", "desktop_mic_optional"}:
            return "desktop_mic_optional"
        if provider in {"ipad", "future_ipad_dictation"}:
            return "future_ipad_dictation"
        return "manual"

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
            self._stt_set_state("ready_to_listen")
            get_logger().log("🎙️ STT 모드 ON: 시작 버튼을 누르면 VAD-only STT 세그먼트를 생성합니다.")
        else:
            session = getattr(self, "_stt_mic_capture_session", None)
            if session is not None and hasattr(session, "stop"):
                try:
                    session.stop()
                except Exception:
                    pass
            self._stt_mic_capture_session = None
            self._stt_recording = False
            self._stt_vad_running = False
            self._stt_set_state("disabled")
            if hasattr(self, "timeline") and hasattr(self.timeline, "canvas"):
                try:
                    self.timeline.canvas.end_mic_visualization()
                except Exception:
                    self.timeline.canvas._is_listening = False
                    self.timeline.canvas.update()
            get_logger().log("🎙️ STT 모드 OFF")
        self._refresh_stt_visuals()

    def _restore_stt_mode_project_state(self, project: dict | None) -> bool:
        try:
            from core.mode_policy import selected_mode_from_settings
            from core.stt_mode.project_state import project_stt_mode_learning, project_stt_mode_state
        except Exception:
            return False

        state = project_stt_mode_state(project)
        learning = project_stt_mode_learning(project)
        project_settings = dict((project or {}).get("user_settings", {}) or {})
        should_enable = bool(state) or selected_mode_from_settings(project_settings) == "stt"
        if not should_enable:
            return False

        self._stt_work_segments = [dict(row) for row in list(state.get("work_segments", []) or []) if isinstance(row, dict)]
        self._stt_raw_dictation_segments = [dict(row) for row in list(state.get("raw_dictation_segments", []) or []) if isinstance(row, dict)]
        self._stt_final_segments = [dict(row) for row in list(state.get("final_segments", []) or []) if isinstance(row, dict)]
        self._stt_rolling_windows = [dict(row) for row in list(state.get("rolling_windows", []) or []) if isinstance(row, dict)]
        self._stt_learning_events = [dict(row) for row in list(learning.get("events", []) or []) if isinstance(row, dict)]
        self._stt_adapter_refs = dict(state.get("adapter_refs", {}) or {})
        self._stt_lora_bundle_info = {
            "bundle_id": str(self._stt_adapter_refs.get("stt_lora_bundle") or ""),
            "adapter_refs": dict(self._stt_adapter_refs),
        }
        self._stt_mode_enabled = True
        try:
            if hasattr(self, "timeline") and hasattr(self.timeline, "set_vad_segments") and self._stt_work_segments:
                self.timeline.set_vad_segments(list(self._stt_work_segments))
        except Exception:
            pass
        self._stt_set_state("ready_to_listen", {"restored": True, "total": len(self._stt_work_segments)})
        self._refresh_stt_visuals()
        try:
            self._refresh_video_subtitle_context()
        except Exception:
            pass
        return True

    def _stt_runtime_policy_bundle(self) -> dict:
        try:
            from core.stt_mode.lora_runtime import build_stt_runtime_policy_bundle

            bundle_base = os.path.splitext(
                os.path.basename(
                    str(getattr(self.window(), "_current_project_path", "") or getattr(self, "media_path", "") or "stt_mode")
                )
            )[0]
            bundle = build_stt_runtime_policy_bundle(
                settings=dict(getattr(self, "settings", {}) or {}),
                work_segments=list(getattr(self, "_stt_work_segments", []) or []),
                raw_segments=list(getattr(self, "_stt_raw_dictation_segments", []) or []),
                final_segments=list(getattr(self, "_stt_final_segments", []) or []),
                learning_events=list(getattr(self, "_stt_learning_events", []) or []),
                bundle_id=f"{bundle_base or 'stt_mode'}_stt_lora",
            )
            if bundle:
                self._stt_lora_bundle_info = dict(bundle)
                self._stt_adapter_refs = dict(bundle.get("adapter_refs", {}) or {})
            return bundle
        except Exception as exc:
            get_logger().log(f"⚠️ STT LoRA 정책 구성 실패: {exc}")
            return {}

    def _stt_cut_boundaries(self) -> list[dict]:
        rows: list[dict] = []
        seen: set[tuple[str, float]] = set()
        for source in (
            list(getattr(self.window(), "_project_boundary_times", []) or []),
            list(getattr(getattr(getattr(self, "timeline", None), "canvas", None), "scan_boundary_times", []) or []),
            list(getattr(self, "_auto_cut_boundary_scan_lines", []) or []),
        ):
            for item in source:
                try:
                    if isinstance(item, dict):
                        sec = float(item.get("time", item.get("start", item.get("timeline_start", 0.0))) or 0.0)
                        key = ("dict", round(sec, 3))
                        payload = dict(item)
                        payload.setdefault("time", sec)
                    else:
                        sec = float(item or 0.0)
                        key = ("time", round(sec, 3))
                        payload = {"time": sec}
                except Exception:
                    continue
                if key in seen:
                    continue
                seen.add(key)
                rows.append(payload)
        rows.sort(key=lambda row: float(row.get("time", row.get("start", row.get("timeline_start", 0.0))) or 0.0))
        return rows

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
        self._stt_set_state("building_segments")
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
            self._stt_set_state("ready_to_listen", {"empty": True})
            return
        self._stt_work_segments = [dict(row) for row in vad_segs if isinstance(row, dict)]
        self._create_stt_segments_from_vad(vad_segs)
        try:
            self.timeline.set_vad_segments(vad_segs)
        except Exception:
            pass
        self._mark_dirty()
        self._stt_set_state("ready_to_listen", {"total": len(vad_segs)})
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
            data.stt_segment_id = str(vad.get("id") or f"stt_segment_{idx + 1:04d}")
            data.stt_mode_status = str(vad.get("stt_mode_status") or "empty")
            data.vad_confidence = vad.get("vad_confidence")
            data.vad_confidence_label = str(vad.get("vad_confidence_label") or "")
            data.vad_decision = str(vad.get("vad_decision") or "")
            data.vad_sources = list(vad.get("vad_sources") or [])
            if data.vad_confidence_label:
                quality_label = {
                    "high": "green",
                    "medium": "yellow",
                    "low": "red",
                    "needs_review": "red",
                }.get(data.vad_confidence_label, "gray")
                data.quality = {
                    "confidence_label": quality_label,
                    "flags": ["stt_vad_confidence"],
                    "vad_confidence_label": data.vad_confidence_label,
                    "vad_confidence": data.vad_confidence,
                }
            for key in (
                "start_frame",
                "end_frame",
                "timeline_start_frame",
                "timeline_end_frame",
                "frame_rate",
                "timeline_frame_rate",
                "frame_range",
                "playback",
            ):
                if key in vad:
                    setattr(data, key, vad.get(key))
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

    def _stt_segment_from_block(self, block) -> dict:
        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData):
            return {}
        start = float(getattr(ud, "start_sec", 0.0) or 0.0)
        end = self._stt_block_end(block, start)
        segment = {
            "id": str(getattr(ud, "stt_segment_id", "") or f"stt_segment_{block.blockNumber() + 1:04d}"),
            "index": int(block.blockNumber()) + 1,
            "line": int(block.blockNumber()),
            "start": start,
            "end": end,
            "timeline_start": start,
            "timeline_end": end,
            "text": block.text().strip(),
            "stt_mode": True,
            "stt_pending": bool(getattr(ud, "stt_pending", False)),
            "stt_mode_status": str(getattr(ud, "stt_mode_status", "") or "empty"),
            "vad_confidence": getattr(ud, "vad_confidence", None),
            "vad_confidence_label": getattr(ud, "vad_confidence_label", ""),
            "vad_decision": getattr(ud, "vad_decision", ""),
            "vad_sources": list(getattr(ud, "vad_sources", []) or []),
        }
        for key in (
            "start_frame",
            "end_frame",
            "timeline_start_frame",
            "timeline_end_frame",
            "frame_rate",
            "timeline_frame_rate",
            "frame_range",
            "playback",
        ):
            if hasattr(ud, key):
                segment[key] = getattr(ud, key)
        return segment

    def _stt_confirm_current_input(self):
        block = self._current_stt_block()
        if not block.isValid():
            return
        text = block.text().strip()
        if not text:
            self._stt_set_state("input_editing", {"needs_text": True})
            self.status_lbl.setText("🎙️ STT 입력 필요: 텍스트를 입력한 뒤 Enter")
            return
        self._apply_stt_text_to_block(block, text, whisper_used=False, input_provider=self._stt_input_provider())
        self._stt_advance_to_next_pending_segment()

    def _apply_stt_text_to_block(
        self,
        block,
        text: str,
        *,
        whisper_used: bool,
        input_provider: str,
    ):
        ud = block.userData()
        if not isinstance(ud, SubtitleBlockData):
            return
        text = str(text or "").strip()
        ud.stt_mode = True
        ud.stt_pending = False
        ud.dictated_text = text
        ud.stt_mode_status = "input_done"
        cur = QTextCursor(self.text_edit.document())
        cur.beginEditBlock()
        cur.setPosition(block.position())
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cur.removeSelectedText()
        cur.insertText(text)
        cur.block().setUserData(ud)
        cur.endEditBlock()
        self.text_edit.setTextCursor(cur)
        self._stt_after_text_applied(cur.block(), text, whisper_used=whisper_used, input_provider=input_provider)

    def _stt_after_text_applied(self, block, text: str, *, whisper_used: bool, input_provider: str):
        try:
            from core.stt_mode.dictation_state import create_raw_dictation_segment, upsert_raw_dictation
            from core.stt_mode.learning_events import create_learning_event
            from core.stt_mode.rolling_resegment import apply_rolling_resegmentation

            work_segment = self._stt_segment_from_block(block)
            raw_segment = create_raw_dictation_segment(
                work_segment,
                text,
                input_provider=input_provider,
                whisper_used=whisper_used,
                settings=dict(getattr(self, "settings", {}) or {}),
                raw_index=len(getattr(self, "_stt_raw_dictation_segments", []) or []) + 1,
            )
            self._stt_raw_dictation_segments = upsert_raw_dictation(
                getattr(self, "_stt_raw_dictation_segments", []),
                raw_segment,
            )
            runtime_bundle = self._stt_runtime_policy_bundle()
            result = apply_rolling_resegmentation(
                raw_segments=self._stt_raw_dictation_segments,
                final_segments=getattr(self, "_stt_final_segments", []),
                current_raw_id=raw_segment.get("id"),
                fps=work_segment.get("timeline_frame_rate") or work_segment.get("frame_rate") or 30.0,
                settings=dict(getattr(self, "settings", {}) or {}),
                stt_lora_policy=runtime_bundle.get("stt_dictation_resegment_policy"),
                subtitle_style_policy=runtime_bundle.get("subtitle_style_policy"),
                cut_boundaries=self._stt_cut_boundaries(),
            )
            self._stt_final_segments = list(result.get("final_segments") or [])
            if result.get("rolling_window"):
                self._stt_rolling_windows.append(dict(result["rolling_window"]))
            self._stt_learning_events.append(
                create_learning_event(
                    "dictation_input_done",
                    {
                        "raw_dictation": raw_segment,
                        "generated_count": len(result.get("generated_segments") or []),
                        "bundle_id": str(runtime_bundle.get("bundle_id") or ""),
                    },
                    project_id=str(getattr(self.window(), "_current_project_path", "") or ""),
                    settings=dict(getattr(self, "settings", {}) or {}),
                )
            )
            self._sync_stt_work_segment_status(work_segment.get("id"), "resegmented")
        except Exception as exc:
            get_logger().log(f"⚠️ STT rolling resegment 실패: {exc}")
        self._mark_dirty()
        self._refresh_stt_visuals()
        self._refresh_video_subtitle_context()
        self._stt_set_state("input_confirmed")

    def _sync_stt_work_segment_status(self, segment_id: str, status: str) -> None:
        for row in getattr(self, "_stt_work_segments", []) or []:
            if str(row.get("id") or "") == str(segment_id or ""):
                row["stt_pending"] = False
                row["stt_mode_status"] = status
                break

    def _stt_advance_to_next_pending_segment(self) -> None:
        doc = self.text_edit.document()
        current_line = self.text_edit.textCursor().blockNumber()
        for start_line in (current_line + 1, 0):
            block = doc.findBlockByNumber(start_line) if start_line else doc.begin()
            while block.isValid():
                ud = block.userData()
                if isinstance(ud, SubtitleBlockData) and not ud.is_gap and getattr(ud, "stt_pending", False):
                    self._select_block(block)
                    self._stt_set_state("next_segment_ready", {"line": block.blockNumber()})
                    return
                block = block.next()
        self._stt_set_state("finished")

    def _handle_stt_enter(self):
        if not getattr(self, "_stt_mode_enabled", False):
            return
        if self._stt_input_provider() != "desktop_mic_optional":
            self._stt_confirm_current_input()
            return
        if self._stt_recording:
            self.status_lbl.setText("🎙️ 녹음 종료 대기...")
            return
        block = self._current_stt_block()
        if not block.isValid():
            return
        self._stt_recording = True
        self._stt_target_line = block.blockNumber()
        self._stt_set_state("input_editing", {"provider": "desktop_mic_optional"})
        self.status_lbl.setText("🎙️ 녹음 중...")
        if hasattr(self, "timeline") and hasattr(self.timeline, "canvas"):
            try:
                self.timeline.canvas.begin_mic_visualization(self._stt_target_line)
            except Exception:
                self.timeline.canvas._is_listening = True
                self.timeline.canvas.update()
        get_logger().log("🎙️ STT 따라말하기 녹음 시작")

        session = None
        try:
            from ui.editor.live_microphone_session import LiveMicrophoneSession

            session = LiveMicrophoneSession(self)
        except Exception as exc:
            self._stt_recording = False
            self.status_lbl.setText("⚠️ 마이크 초기화 실패")
            if hasattr(self, "timeline") and hasattr(self.timeline, "canvas"):
                try:
                    self.timeline.canvas.end_mic_visualization()
                except Exception:
                    self.timeline.canvas._is_listening = False
                    self.timeline.canvas.update()
            get_logger().log(f"⚠️ STT 따라말하기 마이크 초기화 실패: {exc}")
            return

        self._stt_mic_capture_session = session
        if hasattr(self, "timeline") and hasattr(self.timeline, "canvas"):
            canvas = self.timeline.canvas
            try:
                session.waveform_changed.connect(canvas.update_mic_visualization)
            except Exception:
                pass

        def _worker(captured_wav: str, has_audio: bool, error_text: str):
            text = ""
            try:
                from core.audio.live_stt import transcribe_wav_file

                if not has_audio or not captured_wav:
                    if error_text:
                        get_logger().log(f"⚠️ STT 따라말하기 실패: {error_text}")
                    return
                QTimer.singleShot(0, lambda: self.status_lbl.setText("🎙️ STT 처리 중..."))
                result = transcribe_wav_file(captured_wav, profile="quality")
                text = result.text
                if text:
                    get_logger().log(
                        f"🎙️ STT 따라말하기 완료: {result.engine} / {result.model} / {result.elapsed:.1f}s"
                    )
            except Exception as exc:
                get_logger().log(f"⚠️ STT 따라말하기 실패: {exc}")
            finally:
                try:
                    if captured_wav and os.path.exists(captured_wav):
                        os.remove(captured_wav)
                except Exception:
                    pass
                self.sig_live_stt_result.emit(text)

        def _on_capture_finished(captured_wav: str, has_audio: bool, error_text: str, _elapsed: float):
            threading.Thread(
                target=_worker,
                args=(captured_wav, has_audio, error_text),
                daemon=True,
                name="editor-stt-follow-mode",
            ).start()

        session.finished.connect(_on_capture_finished)
        if not session.start():
            self._stt_recording = False
            self._stt_mic_capture_session = None
            self.status_lbl.setText("⚠️ 마이크 시작 실패")
            if hasattr(self, "timeline") and hasattr(self.timeline, "canvas"):
                try:
                    self.timeline.canvas.end_mic_visualization()
                except Exception:
                    self.timeline.canvas._is_listening = False
                    self.timeline.canvas.update()
            return

    def _apply_stt_text_to_current(self, text: str):
        self._stt_recording = False
        self._stt_mic_capture_session = None
        if hasattr(self, "timeline") and hasattr(self.timeline, "canvas"):
            try:
                self.timeline.canvas.end_mic_visualization()
            except Exception:
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
        self._apply_stt_text_to_block(block, text, whisper_used=True, input_provider="desktop_mic_optional")
        self.status_lbl.setText("✅ STT 적용 완료")
        self._stt_advance_to_next_pending_segment()

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
        seg_id = str(getattr(ud, "stt_segment_id", "") or block.blockNumber())
        self._stt_replay_counts[seg_id] = int(self._stt_replay_counts.get(seg_id, 0) or 0) + 1
        self._stt_set_state("playing_segment", {"segment_id": seg_id})
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
        self._stt_set_state("rewind_ready")

    def _warn_pending_stt_before_save(self, segs: list[dict]) -> bool:
        try:
            from core.stt_mode.export_preflight import run_stt_export_preflight

            final_segments = list(getattr(self, "_stt_final_segments", []) or [])
            if not final_segments:
                final_segments = [s for s in segs if not s.get("stt_pending") and str(s.get("text", "") or "").strip()]
            result = run_stt_export_preflight(
                final_segments=final_segments,
                work_segments=list(getattr(self, "_stt_work_segments", []) or []),
                raw_dictation_segments=list(getattr(self, "_stt_raw_dictation_segments", []) or []),
                settings=dict(getattr(self, "settings", {}) or {}),
            )
            if result.get("status") == "ok":
                return True
            pending_count = sum(1 for item in result.get("warnings", []) if item.get("code") == "pending_stt_work_segment")
            if result.get("status") == "blocked":
                QMessageBox.warning(self, "STT 내보내기 확인", "STT 결과에 오류가 있어 SRT 저장 전에 확인이 필요합니다.")
                return False
        except Exception:
            pending_count = len([s for s in segs if s.get("stt_pending")])
        if not pending_count:
            return True
        reply = QMessageBox.warning(
            self,
            "STT 미완료 세그먼트",
            f"완료 전 STT 세그먼트 {pending_count}개는 SRT에 저장되지 않고 프로젝트 상태에만 보존됩니다.\n계속 저장할까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes
