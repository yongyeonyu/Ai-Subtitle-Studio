# Version: 01.00.00
# Phase: PHASE2
from __future__ import annotations

import time
import threading

from PyQt6.QtCore import QTimer


class EditorPipelineStatusMixin:
    def set_live_processing_stage(self, text: str):
        if threading.current_thread() is not threading.main_thread():
            QTimer.singleShot(0, lambda t=str(text or ""): self.set_live_processing_stage(t))
            return
        message = str(text or "").strip()
        if not message:
            self._clear_processing_indicators()
            return
        try:
            sm = getattr(self, "sm", None)
            if sm is not None:
                state = str(getattr(sm, "state", "") or "")
                is_locked = bool(getattr(sm, "is_locked", False))
                if state != "ST_PROC" or not is_locked:
                    self._clear_processing_indicators()
                    return
        except RuntimeError:
            return
        except Exception:
            pass
        now = time.monotonic()
        if (
            message == str(getattr(self, "_last_live_processing_stage", "") or "")
            and now < float(getattr(self, "_next_live_processing_stage_at", 0.0) or 0.0)
        ):
            return
        self._last_live_processing_stage = message
        self._next_live_processing_stage_at = now + 0.25
        try:
            if hasattr(self, "sm") and getattr(self.sm, "is_locked", False):
                self.sm.set_custom_status(message)
            elif hasattr(self, "status_lbl"):
                self.status_lbl.setText(message)
        except RuntimeError:
            return

    def _pipeline_progress_percent(self, c_idx, t_total) -> int:
        total_vid_time = getattr(self.video_player, "total_time", 0.0) if hasattr(self, "video_player") else 0.0
        segs = self._get_current_segments()
        current_end = segs[-1].get("end", 0.0) if segs else 0.0

        if total_vid_time > 0 and current_end > 0:
            return min(100, int((current_end / total_vid_time) * 100))
        if t_total > 0:
            return min(100, int((c_idx / t_total) * 100))
        return 0

    def _update_processing_stage_after_full_progress(self, c_idx, t_total, pct) -> None:
        if not (t_total > 0 and c_idx >= t_total and not getattr(self, "_completion_handled", False)):
            return
        try:
            sm = getattr(self, "sm", None)
            stage_active = bool(sm._is_stage_status_active()) if sm is not None and hasattr(sm, "_is_stage_status_active") else False
            if not stage_active:
                self.sm.update_progress(c_idx, t_total, pct, "⏳ 자막 최적화/검수 중...")
        except Exception:
            pass

    def update_progress(self, c_idx, t_total):
        if threading.current_thread() is not threading.main_thread():
            QTimer.singleShot(0, lambda c=c_idx, t=t_total: self.update_progress(c, t))
            return

        pct = self._pipeline_progress_percent(c_idx, t_total)
        self.sm.update_progress(c_idx, t_total, pct)
        self._update_processing_stage_after_full_progress(c_idx, t_total, pct)

    def _is_final_status_message(self, text, is_final=False, is_raw=False) -> bool:
        _ = is_raw
        return bool(is_final or "에러" in str(text) or "실패" in str(text))

    def update_status(self, text, is_final=False, is_raw=False):
        if threading.current_thread() is not threading.main_thread():
            QTimer.singleShot(0, lambda t=text, f=is_final, r=is_raw: self.update_status(t, f, r))
            return
        if self._is_final_status_message(text, is_final=is_final, is_raw=is_raw):
            if "완료" in str(text):
                self.sm.complete_ai()
            else:
                self.sm.stop_processing(text)
            self._clear_processing_indicators()
        else:
            self.sm.set_custom_status(text)
