# Version: 03.02.13
# Phase: PHASE1-B
"""
ui/queue_widget.py
큐 테이블 + 헤더 + 진행률 + 애니메이션
- main_window.py에서 분리
"""

import time
from PyQt6.QtWidgets import QTableWidgetItem
from PyQt6.QtCore import Qt


class QueueMixin:
    """큐 테이블 관리 (MainWindow에 Mixin으로 결합)"""

    def _animate_queue_status(self):
        self._queue_anim_idx = (self._queue_anim_idx + 1) % len(self._queue_anim_frames)
        for i in range(self.queue_table.rowCount()):
            item = self.queue_table.item(i, 0)
            if item:
                txt = item.text()
                if "자막 생성 중" in txt and "완료" not in txt:
                    item.setText(f"{self._queue_anim_frames[self._queue_anim_idx]} 자막 생성 중")
                elif "자막영상출력" in txt or "영상출력" in txt:
                    item.setText(f"{self._queue_anim_frames[self._queue_anim_idx]} 자막영상출력(mov)")

    def init_queue_list(self, files):
        import os
        if hasattr(self, "_show_bottom_queue_table"):
            self._show_bottom_queue_table()
        self._current_file_idx = 1
        self._total_files = len(files)
        self._expected_seconds = {}
        self._file_start_times = {}
        self._file_complete_times = {}
        self._accumulated_vad = []   # ← 멀티클립 VAD 누적 초기화

        self.queue_table.setUpdatesEnabled(False)
        self.queue_table.setRowCount(0)

        for i, f in enumerate(files):
            self.queue_table.insertRow(i)
            def mk(text):
                it = QTableWidgetItem(text)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                return it
            self.queue_table.setItem(i, 0, mk("⏳ 대기 중"))
            self.queue_table.setItem(i, 1, QTableWidgetItem(os.path.basename(f)))
            self.queue_table.setItem(i, 2, mk("분석 중.."))
            self.queue_table.setItem(i, 3, mk("-"))
            self.queue_table.setItem(i, 4, mk("계산 중"))

        self.queue_table.setUpdatesEnabled(True)

        self.queue_header_lbl.setText(
            f"📋 처리할 파일 리스트 (1 / {len(files)} 진행 중 - 0% 완료 [⏱️ 00:00 / 00:00]"
        )
        self._live_timer.start(1000)

    def update_queue_status(self, idx, status, time_txt="", info_txt="", len_txt=""):
        if hasattr(self, "_show_bottom_queue_table") and status:
            self._show_bottom_queue_table()
        if status:
            self._sync_editor_stage_from_queue_status(status)
        if idx < self.queue_table.rowCount():
            def mk(text):
                it = QTableWidgetItem(text)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                return it
            def fmt(sec):
                try:
                    s = float(sec)
                    m, s = divmod(int(s), 60)
                    h, m = divmod(m, 60)
                    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
                except:
                    return "00:00"
            if status:
                self.queue_table.setItem(idx, 0, mk(status))
                if ("자막 생성 중" in status or "오디오 추출 중" in status) and idx not in self._file_start_times:
                    self._file_start_times[idx] = time.time()
                # ✅ 완료 시 소요시간/예상시간 즉시 기록
                if "완료" in status:
                    self._file_complete_times[idx] = time.time()
                    st = self._file_start_times.get(idx, 0)
                    if st > 0:
                        elapsed = time.time() - st
                        expected = self._expected_seconds.get(idx, 0)
                        e_str = fmt(elapsed)
                        x_str = fmt(expected) if expected > 0 else "?"
                        self.queue_table.setItem(idx, 4, mk(f"{e_str} / {x_str}"))
            if info_txt:
                self.queue_table.setItem(idx, 2, mk(info_txt))
            if len_txt:
                self.queue_table.setItem(idx, 3, mk(len_txt))
            if time_txt:
                try:
                    sec_val = float(time_txt)
                    self._expected_seconds[idx] = sec_val
                    # ✅ 이미 완료된 항목은 time_txt로 덮어쓰지 않음
                    if idx not in self._file_complete_times:
                        self.queue_table.setItem(idx, 4, mk(fmt(sec_val)))
                except (ValueError, TypeError):
                    if idx not in self._file_complete_times:
                        self.queue_table.setItem(idx, 4, mk(time_txt))

    def _sync_editor_stage_from_queue_status(self, status: str):
        editor = getattr(self, "_editor_widget", None)
        state_manager = getattr(editor, "sm", None) if editor is not None else None
        if state_manager is None:
            return
        status_text = str(status or "")
        if "완료" in status_text:
            current_state = str(getattr(state_manager, "state", "") or "")
            if current_state not in {"ST_COMP", "ST_SAVED"}:
                completed = getattr(editor, "_set_process_completed", None)
                if callable(completed):
                    try:
                        completed()
                    except Exception:
                        pass
                else:
                    try:
                        state_manager.complete_auto_mode() if bool(getattr(editor, "is_auto_start", False)) else state_manager.complete_ai()
                    except Exception:
                        pass
            if hasattr(self, "sync_menu_from_editor"):
                self.sync_menu_from_editor(editor)
            if hasattr(self, "_refresh_saved_status_label"):
                dirty_checker = getattr(editor, "_has_unsaved_changes", None)
                if callable(dirty_checker):
                    try:
                        self._refresh_saved_status_label(is_dirty=bool(dirty_checker()))
                    except Exception:
                        self._refresh_saved_status_label()
                else:
                    self._refresh_saved_status_label()
            return
        if str(getattr(state_manager, "state", "") or "") != "ST_PROC":
            return
        try:
            state_manager.set_custom_status(status_text)
        except Exception:
            return
        if hasattr(self, "sync_menu_from_editor"):
            self.sync_menu_from_editor(editor)

    def _update_live_queue_header(self):
        active_backend = None
        if getattr(self, 'backend_fast', None) and getattr(self.backend_fast, '_active', False):
            active_backend = self.backend_fast
        elif self.backend and getattr(self.backend, '_active', False):
            active_backend = self.backend
        if not active_backend:
            return
        if getattr(active_backend, 'pipeline_start_time', 0) == 0:
            return

        now = time.time()
        elapsed = now - active_backend.pipeline_start_time
        expected = getattr(active_backend, 'total_expected_time', 0.0)

        def fmt(sec):
            m, s = divmod(int(sec), 60)
            h, m = divmod(m, 60)
            return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

        c = getattr(self, '_current_file_idx', 1)
        t = getattr(self, '_total_files', 1)
        # 완료 파일 수 기반 진행률
        done_count = 0
        reuse_count = 0
        for i in range(self.queue_table.rowCount()):
            si = self.queue_table.item(i, 0)
            if si:
                st = si.text()
                if '기존자막' in st:
                    reuse_count += 1
                elif '완료' in st:
                    done_count += 1
        if reuse_count >= t and t > 0:
            pct = 100
        else:
            effective_total = max(1, t - reuse_count)
            pct = int((done_count / effective_total) * 100)
        pct = max(0, min(100, pct))
        
        exp_str = fmt(expected) if expected > 0 else "예상불가"

        self.queue_header_lbl.setText(
            f"📋 처리할 파일 리스트 ({c} / {t} 진행 중) - {pct}% 완료   [⏱️ {fmt(elapsed)} / {exp_str}]"
        )

        for i in range(self.queue_table.rowCount()):
            si = self.queue_table.item(i, 0)
            if not si:
                continue
            status_text = si.text()
            if "완료" in status_text:
                continue
            if "자막 생성 중" in status_text:
                st = self._file_start_times.get(i, now)
                ef = now - st
                xf = self._expected_seconds.get(i, 0)
                tc = self.queue_table.item(i, 4)
                if tc:
                    tc.setText(f"{fmt(ef)} / {fmt(xf) if xf > 0 else '학습 중'}")

    def update_queue_header(self, current, total, pct, eta_str=""):
        if hasattr(self, "_show_bottom_queue_table"):
            self._show_bottom_queue_table()
        self._current_file_idx = current
        self._total_files = total
        self._real_pct = pct  # ✅ 이 줄 추가
        if pct == 100:
            if hasattr(self, '_live_timer'):
                self._live_timer.stop()
            self.queue_header_lbl.setText(
                f"📋 처리할 파일 리스트 ({total} / {total} 완료) - 100% 완료"
            )
