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
from PyQt6.QtGui import QColor


class QueueMixin:
    """큐 테이블 관리 (MainWindow에 Mixin으로 결합)"""

    def clear_queue_list(self, header: str = "큐 리스트 : (0/0) - 0% 완료"):
        table = getattr(self, "queue_table", None)
        if table is not None:
            table.setRowCount(0)
        label = getattr(self, "queue_header_lbl", None)
        if label is not None:
            label.setText(str(header or "큐 리스트 : (0/0) - 0% 완료"))
        self._current_file_idx = 0
        self._total_files = 0
        self._real_pct = 0
        self._expected_seconds = {}
        self._file_start_times = {}
        self._file_complete_times = {}
        self._sidebar_queue_cache_items = []
        self._sidebar_queue_cache_header = str(header or "큐 리스트 : (0/0) - 0% 완료")
        if hasattr(self, "_live_timer"):
            self._live_timer.stop()
        if hasattr(self, "_sync_sidebar_queue_panel"):
            self._sync_sidebar_queue_panel()

    def _queue_status_flags(self, status: str) -> tuple[bool, bool, bool]:
        text = str(status or "")
        stripped = text.strip()
        stage_done_only = "컷 경계" in stripped and "완료" in stripped
        done = (
            not stage_done_only
            and "미완료" not in stripped
            and (
                stripped in {"완료", "✅기존자막", "기존자막"}
                or stripped.startswith("✅")
                and "완료" in stripped
                or "기존자막" in stripped
            )
        )
        error = any(token in text for token in ("오류", "실패", "중단"))
        active = not done and not error and not any(token in text for token in ("대기", "-"))
        return done, error, active

    def _queue_status_restarts_completed_row(self, idx: int, status: str) -> bool:
        text = str(status or "").strip()
        if not text:
            return False
        done, error, _active = self._queue_status_flags(text)
        if done or error:
            return False
        early_stage_tokens = (
            "재시작",
            "컷 경계",
            "오디오 추출",
            "[전처리]",
            "[음성]",
            "[stt",
            "whisper",
            "[stt+자막 llm]",
            "자막 생성 중",
        )
        if (
            int(getattr(self, "_real_pct", 0) or 0) >= 100
            and int(idx) == int(self._current_queue_active_row())
            and any(token in text.lower() for token in early_stage_tokens)
        ):
            return True
        return (
            "재시작" in text
            or "오디오 추출" in text
            or text.startswith("⏳ [전처리]")
        )

    def _reset_completed_queue_row_for_restart(self, idx: int):
        if hasattr(self, "_file_complete_times"):
            self._file_complete_times.pop(idx, None)
        if hasattr(self, "_file_start_times"):
            self._file_start_times.pop(idx, None)
        self._real_pct = 0
        try:
            self._current_file_idx = idx + 1
            total = int(getattr(self, "_total_files", 0) or self.queue_table.rowCount())
            if total <= 0:
                total = self.queue_table.rowCount()
            eta_item = self.queue_table.item(idx, 4)
            if eta_item is not None:
                eta_item.setText("계산 중")
            label = getattr(self, "queue_header_lbl", None)
            if label is not None:
                label.setText(f"큐 리스트 : ({idx + 1}/{total}) - 0% 완료")
            timer = getattr(self, "_live_timer", None)
            if timer is not None:
                timer.start(1000)
        except Exception:
            pass

    def _queue_card_time_text(self, eta_text: str, duration_text: str) -> str:
        eta = str(eta_text or "-").strip() or "-"
        if eta in {"?", "계산 중", "분석 중..", "예상불가"}:
            eta = "-"
        if "/" in eta:
            left, right = [part.strip() for part in eta.split("/", 1)]
            left = left or "00:00"
            right = "-" if right in {"", "?", "계산 중", "분석 중..", "예상불가"} else right
            return f"{left} / {right}"
        if eta == "-":
            return "-"
        return f"00:00 / {eta}"

    def _current_queue_active_row(self) -> int:
        table = getattr(self, "queue_table", None)
        if table is None:
            return -1
        try:
            row = int(getattr(self, "_current_file_idx", 1) or 1) - 1
        except Exception:
            row = 0
        return row if 0 <= row < table.rowCount() else -1

    def _apply_queue_row_visual_state(self, row: int):
        table = getattr(self, "queue_table", None)
        if table is None or row < 0 or row >= table.rowCount():
            return
        status_item = table.item(row, 0)
        status = str(status_item.text() if status_item else "")
        done, error, status_active = self._queue_status_flags(status)
        active = status_active and row == self._current_queue_active_row()
        if done:
            fg = QColor("#55D97A")
            bg = QColor("#13261D")
        elif error:
            fg = QColor("#FF6B78")
            bg = QColor("#291719")
        elif active:
            fg = QColor("#FFD84D")
            bg = QColor("#15212A")
        else:
            fg = QColor("#9DB0BB")
            bg = QColor("#121A1E")
        for col in range(table.columnCount()):
            item = table.item(row, col)
            if item is None:
                continue
            item.setForeground(fg)
            item.setBackground(bg)

    def _mark_prior_queue_rows_done(self, current_one_based: int):
        table = getattr(self, "queue_table", None)
        if table is None:
            return
        try:
            boundary = min(max(0, int(current_one_based) - 1), table.rowCount())
        except Exception:
            return
        for row in range(boundary):
            status_item = table.item(row, 0)
            status_text = str(status_item.text() if status_item else "")
            done, error, _active = self._queue_status_flags(status_text)
            if error:
                self._apply_queue_row_visual_state(row)
                continue
            if not done:
                if status_item is None:
                    status_item = QTableWidgetItem("✅ 완료")
                    status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table.setItem(row, 0, status_item)
                else:
                    status_item.setText("✅ 완료")
                    status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if hasattr(self, "_file_complete_times"):
                    self._file_complete_times.setdefault(row, time.time())
            self._apply_queue_row_visual_state(row)

    def _animate_queue_status(self):
        self._queue_anim_idx = (self._queue_anim_idx + 1) % len(self._queue_anim_frames)
        for i in range(self.queue_table.rowCount()):
            item = self.queue_table.item(i, 0)
            if item:
                txt = item.text()
                if "자막 생성 중" in txt and "완료" not in txt:
                    item.setText("자막 생성 중")
                elif "자막영상출력" in txt or "영상출력" in txt:
                    item.setText("자막영상출력(mov)")

    def init_queue_list(self, files):
        import os
        if hasattr(self, "_show_bottom_queue_table"):
            self._show_bottom_queue_table()
        self._current_file_idx = 1
        self._total_files = len(files)
        self._expected_seconds = {}
        self._file_start_times = {}
        self._file_complete_times = {}
        self._real_pct = 0
        if files:
            self._sidebar_queue_cache_items = []
            self._sidebar_queue_cache_header = ""
        self._accumulated_vad = []   # ← 멀티클립 VAD 누적 초기화

        self.queue_table.setUpdatesEnabled(False)
        self.queue_table.setRowCount(0)

        for i, f in enumerate(files):
            self.queue_table.insertRow(i)
            def mk(text):
                it = QTableWidgetItem(text)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                return it
            self.queue_table.setItem(i, 0, mk("대기 중"))
            self.queue_table.setItem(i, 1, QTableWidgetItem(os.path.basename(f)))
            self.queue_table.setItem(i, 2, mk("분석 중.."))
            self.queue_table.setItem(i, 3, mk("-"))
            self.queue_table.setItem(i, 4, mk("계산 중"))
            self._apply_queue_row_visual_state(i)

        self.queue_table.setUpdatesEnabled(True)

        self.queue_header_lbl.setText(f"큐 리스트 : (1/{len(files)}) - 0% 완료")
        if hasattr(self, "_refresh_sidebar_queue_cache"):
            self._refresh_sidebar_queue_cache()
        if hasattr(self, "_sync_sidebar_queue_panel"):
            self._sync_sidebar_queue_panel()
        self._live_timer.start(1000)

    def update_queue_status(self, idx, status, time_txt="", info_txt="", len_txt=""):
        if hasattr(self, "_show_bottom_queue_table") and status:
            self._show_bottom_queue_table()
        engine_dirty = False
        if 0 <= idx < self.queue_table.rowCount():
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
            incoming_done, incoming_error, incoming_active = self._queue_status_flags(status)
            try:
                current_idx = int(getattr(self, "_current_file_idx", 0) or 0)
            except Exception:
                current_idx = 0
            if (incoming_done or incoming_error or incoming_active) and idx + 1 > current_idx:
                self._current_file_idx = idx + 1
            if idx > 0 and (incoming_done or incoming_error or incoming_active):
                self._mark_prior_queue_rows_done(idx + 1)
            current_status_item = self.queue_table.item(idx, 0)
            current_status = str(current_status_item.text() if current_status_item else "")
            current_done, current_error, current_active = self._queue_status_flags(current_status)
            if current_done and not incoming_done:
                if self._queue_status_restarts_completed_row(idx, status):
                    self._reset_completed_queue_row_for_restart(idx)
                    current_done = False
                else:
                    self._apply_queue_row_visual_state(idx)
                    if hasattr(self, "_sync_sidebar_queue_panel"):
                        if hasattr(self, "_refresh_sidebar_queue_cache"):
                            self._refresh_sidebar_queue_cache()
                        self._sync_sidebar_queue_panel()
                    if hasattr(self, "_refresh_sidebar_engine_info"):
                        self._refresh_sidebar_engine_info()
                    return
            if current_error and not (incoming_error or incoming_done):
                self._apply_queue_row_visual_state(idx)
                if hasattr(self, "_sync_sidebar_queue_panel"):
                    if hasattr(self, "_refresh_sidebar_queue_cache"):
                        self._refresh_sidebar_queue_cache()
                    self._sync_sidebar_queue_panel()
                if hasattr(self, "_refresh_sidebar_engine_info"):
                    self._refresh_sidebar_engine_info()
                return
            apply_status = status
            if current_active and not (incoming_done or incoming_error or incoming_active):
                apply_status = ""
            if apply_status:
                self._sync_editor_stage_from_queue_status(apply_status)
                engine_dirty = True
            if apply_status:
                self.queue_table.setItem(idx, 0, mk(apply_status))
                if ("자막 생성 중" in apply_status or "오디오 추출 중" in apply_status) and idx not in self._file_start_times:
                    self._file_start_times[idx] = time.time()
                # ✅ 완료 시 소요시간/예상시간 즉시 기록
                if self._queue_status_flags(apply_status)[0]:
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
            self._apply_queue_row_visual_state(idx)
        if hasattr(self, "_sync_sidebar_queue_panel"):
            if hasattr(self, "_refresh_sidebar_queue_cache"):
                self._refresh_sidebar_queue_cache()
            self._sync_sidebar_queue_panel()
        if engine_dirty and hasattr(self, "_refresh_sidebar_engine_info"):
            self._refresh_sidebar_engine_info()

    def _sync_editor_stage_from_queue_status(self, status: str):
        editor = getattr(self, "_editor_widget", None)
        state_manager = getattr(editor, "sm", None) if editor is not None else None
        if state_manager is None:
            return
        status_text = str(status or "")
        if "컷 경계" in status_text and "완료" in status_text:
            try:
                state_manager.set_custom_status(status_text)
            except Exception:
                pass
            if hasattr(self, "_refresh_sidebar_engine_info"):
                self._refresh_sidebar_engine_info()
            return
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
        def fmt(sec):
            m, s = divmod(int(sec), 60)
            h, m = divmod(m, 60)
            return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

        c = getattr(self, '_current_file_idx', 1)
        t = getattr(self, '_total_files', 1)
        self._mark_prior_queue_rows_done(c)
        # 완료 파일 수 기반 진행률
        done_count = 0
        reuse_count = 0
        for i in range(self.queue_table.rowCount()):
            si = self.queue_table.item(i, 0)
            if si:
                st = si.text()
                row_done, _row_error, _row_active = self._queue_status_flags(st)
                if '기존자막' in st:
                    reuse_count += 1
                elif row_done:
                    done_count += 1
        if reuse_count >= t and t > 0:
            pct = 100
        else:
            effective_total = max(1, t - reuse_count)
            pct = int((done_count / effective_total) * 100)
        pct = max(0, min(100, pct))
        
        self.queue_header_lbl.setText(f"큐 리스트 : ({c}/{t}) - {pct}% 완료")

        for i in range(self.queue_table.rowCount()):
            si = self.queue_table.item(i, 0)
            if not si:
                continue
            status_text = si.text()
            row_done, _row_error, _row_active = self._queue_status_flags(status_text)
            if row_done:
                self._apply_queue_row_visual_state(i)
                continue
            if "자막 생성 중" in status_text:
                st = self._file_start_times.get(i, now)
                ef = now - st
                xf = self._expected_seconds.get(i, 0)
                tc = self.queue_table.item(i, 4)
                if tc:
                    tc.setText(f"{fmt(ef)} / {fmt(xf) if xf > 0 else '학습 중'}")
            self._apply_queue_row_visual_state(i)
        if hasattr(self, "_sync_sidebar_queue_panel"):
            if hasattr(self, "_refresh_sidebar_queue_cache"):
                self._refresh_sidebar_queue_cache()
            self._sync_sidebar_queue_panel()
        if hasattr(self, "_refresh_sidebar_engine_info"):
            self._refresh_sidebar_engine_info()

    def update_queue_header(self, current, total, pct, eta_str=""):
        if hasattr(self, "_show_bottom_queue_table"):
            self._show_bottom_queue_table()
        try:
            current = int(current)
        except Exception:
            current = int(getattr(self, "_current_file_idx", 1) or 1)
        try:
            total = int(total)
        except Exception:
            total = int(getattr(self, "_total_files", 1) or 1)
        try:
            pct = int(pct)
        except Exception:
            pct = int(getattr(self, "_real_pct", 0) or 0)
        prev_current = int(getattr(self, "_current_file_idx", 0) or 0)
        prev_pct = int(getattr(self, "_real_pct", 0) or 0)
        if prev_current > 1 and 0 < current < prev_current:
            current = prev_current
        final_signal = pct >= 100 and total > 0 and current >= total
        allow_restart_reset = False
        if prev_pct >= 100 and pct <= 0 and current <= max(prev_current, 1):
            try:
                active_row = max(0, min(self.queue_table.rowCount() - 1, current - 1))
                status_item = self.queue_table.item(active_row, 0)
                status_text = str(status_item.text() if status_item else "")
                row_done, row_error, row_active = self._queue_status_flags(status_text)
                allow_restart_reset = not row_done and not row_error and (
                    row_active or "대기" in status_text
                )
            except Exception:
                allow_restart_reset = False
        if not final_signal and pct < prev_pct and current <= max(prev_current, 1) and not allow_restart_reset:
            pct = prev_pct
        self._current_file_idx = current
        self._total_files = total
        self._mark_prior_queue_rows_done(current)
        row_statuses = []
        try:
            for i in range(self.queue_table.rowCount()):
                item = self.queue_table.item(i, 0)
                row_statuses.append(item.text() if item else "")
        except Exception:
            row_statuses = []
        all_rows_done = bool(row_statuses) and all(self._queue_status_flags(st)[0] for st in row_statuses)
        if pct == 100 and row_statuses and not all_rows_done:
            pct = 0 if all("대기" in st for st in row_statuses) else min(99, max(0, int(pct)))
        self._real_pct = pct
        if pct == 100 and all_rows_done:
            for row in range(self.queue_table.rowCount()):
                status_item = self.queue_table.item(row, 0)
                status_text = str(status_item.text() if status_item else "")
                if any(token in status_text for token in ("오류", "실패", "중단")):
                    continue
                done_text = "✅기존자막" if "기존자막" in status_text else "✅ 완료"
                if status_item is None:
                    status_item = QTableWidgetItem(done_text)
                    status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.queue_table.setItem(row, 0, status_item)
                else:
                    status_item.setText(done_text)
                    status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._apply_queue_row_visual_state(row)
            if hasattr(self, '_live_timer'):
                self._live_timer.stop()
            self.queue_header_lbl.setText(f"큐 리스트 : ({total}/{total}) - 100% 완료")
        else:
            self.queue_header_lbl.setText(f"큐 리스트 : ({current}/{total}) - {pct}% 완료")
        if hasattr(self, "_refresh_sidebar_queue_cache"):
            self._refresh_sidebar_queue_cache()
        if hasattr(self, "_sync_sidebar_queue_panel"):
            self._sync_sidebar_queue_panel()
        if hasattr(self, "_refresh_sidebar_engine_info"):
            self._refresh_sidebar_engine_info()

    def _refresh_sidebar_queue_cache(self):
        table = getattr(self, "queue_table", None)
        label = getattr(self, "queue_header_lbl", None)
        items = []
        active_row = self._current_queue_active_row()
        if table is not None:
            try:
                for row in range(table.rowCount()):
                    status_item = table.item(row, 0)
                    file_item = table.item(row, 1)
                    duration_item = table.item(row, 3)
                    eta_item = table.item(row, 4)
                    raw_status = str(status_item.text() if status_item else "-")
                    done, error, status_active = self._queue_status_flags(raw_status)
                    status = self._plain_queue_status(raw_status) if hasattr(self, "_plain_queue_status") else raw_status
                    active = status_active and row == active_row
                    display_status = "완료" if done else status
                    items.append({
                        "order": str(row + 1),
                        "status": status,
                        "statusDisplay": display_status,
                        "done": done,
                        "active": active,
                        "error": error,
                        "file": str(file_item.text() if file_item else "-"),
                        "eta": self._queue_card_time_text(
                            str(eta_item.text() if eta_item else "-"),
                            str(duration_item.text() if duration_item else "-"),
                        ),
                    })
            except RuntimeError:
                items = list(getattr(self, "_sidebar_queue_cache_items", []) or [])
        if items or not list(getattr(self, "_sidebar_queue_cache_items", []) or []):
            self._sidebar_queue_cache_items = items
        try:
            header = str(label.text() if label is not None else "")
        except RuntimeError:
            header = ""
        self._sidebar_queue_cache_header = header
