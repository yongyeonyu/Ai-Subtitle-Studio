# Version: 03.02.13
# Phase: PHASE1-B
"""
ui/queue_widget.py
큐 테이블 + 헤더 + 진행률 + 애니메이션
- main_window.py에서 분리
"""

import os
import time
from PyQt6.QtWidgets import QTableWidgetItem
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from core.runtime.logger import get_logger
from core.pipeline_status import is_generation_stage_status
from ui.queue.queue_formatting import (
    build_queue_sidebar_item,
    normalize_queue_header_payload,
    normalize_queue_header_text,
    normalize_queue_status_payload,
    DEFAULT_QUEUE_HEADER,
    format_queue_card_time,
    format_queue_clock,
    format_queue_header,
    parse_queue_seconds_value,
    queue_expected_display_text,
    queue_expected_time_is_unknown,
    queue_status_flags,
)
from ui.queue.queue_state_model import QueueStateModel, normalize_queue_row_snapshot
from ui.style import COLORS


class QueueMixin:
    """큐 테이블 관리 (MainWindow에 Mixin으로 결합)"""

    def _queue_log_nonfatal(self, step: str, exc: BaseException) -> None:
        get_logger().log(
            f"⚠️ 큐 상태 처리 실패 [{step}]: {exc}",
            level="WARN",
            stage="queue",
        )

    def _queue_table_ref(self):
        return getattr(self, "queue_table", None)

    def _queue_header_label_ref(self):
        return getattr(self, "queue_header_lbl", None)

    def _make_queue_table_item(self, text, *, center: bool = True) -> QTableWidgetItem:
        item = QTableWidgetItem(str(text or ""))
        if center:
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return item

    def _queue_table_item(self, row: int, col: int):
        table = self._queue_table_ref()
        if table is None:
            return None
        try:
            return table.item(int(row), int(col))
        except Exception:
            return None

    def _queue_row_items(self, row: int):
        table = self._queue_table_ref()
        if table is None:
            return []
        try:
            row_idx = int(row)
        except Exception:
            return []
        if row_idx < 0 or row_idx >= self._queue_row_count():
            return []
        items = []
        for col in range(table.columnCount()):
            item = self._queue_table_item(row_idx, col)
            if item is not None:
                items.append(item)
        return items

    def _queue_table_item_text(self, row: int, col: int) -> str:
        item = self._queue_table_item(row, col)
        try:
            return str(item.text() if item is not None else "")
        except Exception:
            return ""

    def _set_queue_table_item_text(self, row: int, col: int, text, *, center: bool = True):
        table = self._queue_table_ref()
        if table is None:
            return None
        item = self._queue_table_item(row, col)
        if item is None:
            item = self._make_queue_table_item(text, center=center)
            try:
                table.setItem(int(row), int(col), item)
            except Exception:
                return None
            return item
        try:
            item.setText(str(text or ""))
            if center:
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        except Exception:
            return None
        return item

    def _set_queue_header_text(self, text) -> None:
        header_text = str(text or DEFAULT_QUEUE_HEADER)
        state_model = getattr(self, "_queue_state_model", None)
        if isinstance(state_model, QueueStateModel):
            self._queue_state_model = state_model.with_header(header_text)
        label = self._queue_header_label_ref()
        if label is None:
            return
        try:
            label.setText(header_text)
        except Exception:
            return

    def _clear_queue_table_rows(self) -> None:
        table = self._queue_table_ref()
        if table is None:
            return
        try:
            table.setRowCount(0)
        except Exception:
            return

    def _insert_queue_table_row(self, row: int) -> bool:
        table = self._queue_table_ref()
        if table is None:
            return False
        try:
            table.insertRow(int(row))
        except Exception:
            return False
        return True

    def _populate_queue_table_row(
        self,
        row: int,
        *,
        status_text,
        file_text,
        info_text,
        duration_text,
        eta_text,
    ) -> dict[str, object]:
        self._set_queue_table_item_text(row, 0, status_text)
        self._set_queue_table_item_text(row, 1, file_text, center=False)
        self._set_queue_table_item_text(row, 2, info_text)
        self._set_queue_table_item_text(row, 3, duration_text)
        self._set_queue_table_item_text(row, 4, eta_text)
        self._apply_queue_row_visual_state(row)
        return self.queue_row_snapshot(row)

    def _refresh_queue_sidebar_views(self) -> None:
        self.refresh_queue_views()

    def refresh_queue_views(self) -> None:
        if hasattr(self, "_refresh_sidebar_queue_cache"):
            self._refresh_sidebar_queue_cache()
        syncer = getattr(self, "sync_sidebar_queue_panel", None)
        synced = False
        if callable(syncer):
            try:
                synced = bool(syncer())
            except Exception:
                synced = False
        if synced:
            return
        if hasattr(self, "_sync_sidebar_queue_panel"):
            self._sync_sidebar_queue_panel()

    def _format_queue_clock(self, sec) -> str:
        return format_queue_clock(sec)

    def _parse_queue_seconds_value(self, value) -> float | None:
        return parse_queue_seconds_value(value)

    def _queue_expected_time_is_unknown(self, value) -> bool:
        return queue_expected_time_is_unknown(value)

    def _queue_expected_display_text(self, value) -> str:
        return queue_expected_display_text(value)

    def _queue_expected_time_label(self, idx: int, eta_text: str = "", duration_text: str = "") -> str:
        expected = self._expected_seconds.get(idx, 0)
        if expected > 0:
            return self._format_queue_clock(expected)
        eta = str(eta_text or "").strip()
        if "/" in eta:
            _left, right = [part.strip() for part in eta.split("/", 1)]
            eta = right
        if eta and not self._queue_expected_time_is_unknown(eta):
            return eta
        duration = str(duration_text or "").strip()
        if duration and not self._queue_expected_time_is_unknown(duration):
            return duration
        return "예상불가"

    def clear_queue_list(self, header: str = DEFAULT_QUEUE_HEADER):
        self._clear_queue_table_rows()
        header_text = str(header or DEFAULT_QUEUE_HEADER)
        self._set_queue_header_text(header_text)
        self._current_file_idx = 0
        self._total_files = 0
        self._real_pct = 0
        self._expected_seconds = {}
        self._file_start_times = {}
        self._file_complete_times = {}
        self._queue_execution_started_at = 0.0
        self._queue_row_cache = []
        self._sidebar_queue_cache_items = []
        self._sidebar_queue_cache_header = header_text
        self._queue_state_model = QueueStateModel.empty(header_text)
        if hasattr(self, "_live_timer"):
            self._live_timer.stop()
        self._refresh_queue_sidebar_views()

    def _queue_status_flags(self, status: str) -> tuple[bool, bool, bool]:
        return queue_status_flags(status)

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

    def _queue_status_reopens_completed_row_for_followup(self, status: str) -> bool:
        text = str(status or "").strip().lower()
        if not text:
            return False
        return "러프컷" in text and ("llm" in text or "후처리" in text)

    def _reset_completed_queue_row_for_restart(
        self,
        idx: int,
        *,
        preserve_start_time: bool = False,
        preserve_progress: bool = False,
    ):
        if hasattr(self, "_file_complete_times"):
            self._file_complete_times.pop(idx, None)
        if not preserve_start_time and hasattr(self, "_file_start_times"):
            self._file_start_times.pop(idx, None)
        if not preserve_progress:
            self._real_pct = 0
        try:
            self._current_file_idx = idx + 1
            total = int(getattr(self, "_total_files", 0) or self._queue_row_count())
            if total <= 0:
                total = self._queue_row_count()
            if not preserve_start_time:
                self._set_queue_table_item_text(idx, 4, "계산 중")
            if not preserve_progress:
                self._set_queue_header_text(format_queue_header(idx + 1, total, 0))
            timer = getattr(self, "_live_timer", None)
            if timer is not None:
                timer.start(1000)
        except (RuntimeError, AttributeError, TypeError, ValueError) as exc:
            self._queue_log_nonfatal("restart reset", exc)

    def _queue_card_time_text(self, eta_text: str, duration_text: str) -> str:
        return format_queue_card_time(eta_text, duration_text)

    def _current_queue_active_row(self) -> int:
        row_count = self._queue_row_count()
        if row_count <= 0:
            return -1
        try:
            row = int(getattr(self, "_current_file_idx", 1) or 1) - 1
        except Exception:
            row = 0
        return row if 0 <= row < row_count else -1

    def queue_active_row_index(self) -> int:
        return self._current_queue_active_row()

    def queue_row_count(self) -> int:
        return self._queue_row_count()

    def queue_progress_state(self) -> dict[str, int]:
        return {
            "current": max(0, int(getattr(self, "_current_file_idx", 0) or 0)),
            "total": max(0, int(getattr(self, "_total_files", 0) or 0)),
            "pct": max(0, int(getattr(self, "_real_pct", 0) or 0)),
        }

    def queue_sidebar_header_text(self) -> str:
        raw = ""
        label = self._queue_header_label_ref()
        if label is not None:
            try:
                raw = str(label.text() or "")
            except RuntimeError:
                raw = ""
        if not raw:
            raw = str(getattr(self, "_sidebar_queue_cache_header", "") or "")
        if not raw:
            state_model = getattr(self, "_queue_state_model", None)
            if isinstance(state_model, QueueStateModel):
                raw = str(state_model.header or "")
        progress = self.queue_progress_state()
        return normalize_queue_header_text(
            raw,
            current=progress["current"],
            total=progress["total"],
            pct=progress["pct"],
        )

    def _queue_row_count(self) -> int:
        table = self._queue_table_ref()
        if table is None:
            state_model = getattr(self, "_queue_state_model", None)
            if isinstance(state_model, QueueStateModel):
                return state_model.row_count()
            return 0
        try:
            return max(0, int(table.rowCount()))
        except Exception:
            return 0

    def _queue_row_indices(self):
        return range(self._queue_row_count())

    def queue_row_snapshot(self, row: int) -> dict[str, object]:
        try:
            row_idx = int(row)
        except Exception:
            row_idx = -1
        if row_idx < 0:
            return {}
        table = self._queue_table_ref()
        if table is None:
            state_model = getattr(self, "_queue_state_model", None)
            if isinstance(state_model, QueueStateModel):
                snapshot = state_model.row_snapshot(row_idx)
                if snapshot:
                    return snapshot
            cache = list(getattr(self, "_queue_row_cache", []) or [])
            if 0 <= row_idx < len(cache):
                item = dict(cache[row_idx] or {})
                return normalize_queue_row_snapshot(row_idx, item)
            return {}
        if row_idx >= self._queue_row_count():
            return {}
        return {
            "row": row_idx,
            "status": self._queue_table_item_text(row_idx, 0),
            "file": self._queue_table_item_text(row_idx, 1),
            "info": self._queue_table_item_text(row_idx, 2),
            "duration": self._queue_table_item_text(row_idx, 3),
            "eta": self._queue_table_item_text(row_idx, 4),
        }

    def _queue_row_status_state(self, row: int) -> dict[str, object]:
        snapshot = self.queue_row_snapshot(row)
        status_text = str(snapshot.get("status", "") or "")
        done, error, status_active = self._queue_status_flags(status_text)
        return {
            "row": int(snapshot.get("row", row) or row),
            "status": status_text,
            "done": bool(done),
            "error": bool(error),
            "status_active": bool(status_active),
        }

    def _set_queue_row_status_text(self, row: int, text) -> None:
        self._set_queue_table_item_text(row, 0, text)

    def _queue_row_visual_palette(self, row: int) -> tuple[QColor, QColor]:
        state = self._queue_row_status_state(row)
        active = bool(state["status_active"]) and int(state["row"]) == self._current_queue_active_row()
        if state["done"]:
            return QColor("#55D97A"), QColor("#13261D")
        if state["error"]:
            return QColor("#FF6B78"), QColor("#291719")
        if active:
            return QColor(COLORS["warning"]), QColor(COLORS["warning_surface_alt_soft"])
        return QColor("#9DB0BB"), QColor("#121A1E")

    def _queue_sidebar_item_for_row(
        self,
        row: int,
        *,
        snapshot: dict[str, object] | None = None,
        active_row: int | None = None,
    ) -> dict[str, object]:
        row_idx = int(row)
        row_snapshot = dict(snapshot or self.queue_row_snapshot(row_idx) or {})
        if active_row is None:
            active_row = self._current_queue_active_row()
        return build_queue_sidebar_item(
            order=row_idx + 1,
            raw_status=str(row_snapshot.get("status", "-") or "-"),
            file_text=str(row_snapshot.get("file", "-") or "-"),
            info_text=str(row_snapshot.get("info", "-") or "-"),
            eta_text=str(row_snapshot.get("eta", "-") or "-"),
            duration_text=str(row_snapshot.get("duration", "-") or "-"),
            active=(row_idx == int(active_row)),
        )

    def _queue_sidebar_placeholder_item(self, order: int) -> dict[str, object]:
        return build_queue_sidebar_item(
            order=max(1, int(order)),
            raw_status="-",
            file_text="-",
            info_text="-",
            eta_text="-",
            duration_text="-",
            active=False,
        )

    def _set_queue_row_cache_entry(self, row: int, entry: dict[str, object]) -> None:
        try:
            row_idx = int(row)
        except Exception:
            return
        if row_idx < 0:
            return
        cache = list(getattr(self, "_queue_row_cache", []) or [])
        while len(cache) <= row_idx:
            cache.append(self._queue_sidebar_placeholder_item(len(cache) + 1))
        cache[row_idx] = dict(entry or self._queue_sidebar_placeholder_item(row_idx + 1))
        self._queue_row_cache = cache
        state_model = getattr(self, "_queue_state_model", None)
        if not isinstance(state_model, QueueStateModel):
            state_model = QueueStateModel.empty(str(getattr(self, "_sidebar_queue_cache_header", "") or ""))
        self._queue_state_model = state_model.with_row(row_idx, cache[row_idx])

    def _queue_row_cache_items_copy(self) -> list[dict]:
        return [dict(item) for item in list(getattr(self, "_queue_row_cache", []) or [])]

    def _sidebar_queue_cache_items_copy(self) -> list[dict]:
        return [dict(item) for item in list(getattr(self, "_sidebar_queue_cache_items", []) or [])]

    def _queue_sidebar_items_from_cache(self) -> list[dict]:
        items = self._queue_row_cache_items_copy()
        if items:
            return items
        return self._sidebar_queue_cache_items_copy()

    def find_queue_row_for_media(self, media_path: str = "", current_row_hint=None) -> int | None:
        table = self._queue_table_ref()
        row_count = self._queue_row_count()
        if table is None or row_count <= 0:
            return None

        candidates: list[int] = []
        hint = current_row_hint
        if hint is None:
            try:
                hint = int(getattr(self, "_current_file_idx", 1) or 1) - 1
            except Exception:
                hint = None
        try:
            if hint is not None:
                hint_idx = int(hint)
                if 0 <= hint_idx < row_count:
                    candidates.append(hint_idx)
        except (TypeError, ValueError):
            pass

        media_name = os.path.basename(str(media_path or "")).strip().lower()
        if media_name:
            for row in self._queue_row_indices():
                item_name = os.path.basename(self._queue_table_item_text(row, 1)).strip().lower()
                if item_name == media_name and row not in candidates:
                    candidates.append(row)

        if not candidates and row_count == 1:
            return 0

        for row in candidates:
            try:
                status_text = self._queue_table_item_text(row, 0)
                if "완료" not in status_text and "기존자막" not in status_text:
                    return row
            except Exception:
                continue
        return candidates[0] if candidates else None

    def queue_row_status_text(self, row: int) -> str:
        table = self._queue_table_ref()
        if table is None or row < 0:
            return ""
        return self._queue_table_item_text(int(row), 0)

    def queue_row_expected_seconds(self, row: int) -> float:
        try:
            expected = float((getattr(self, "_expected_seconds", {}) or {}).get(int(row), 0.0) or 0.0)
        except Exception:
            expected = 0.0
        if expected > 0:
            return expected
        table = self._queue_table_ref()
        if table is None or row < 0:
            return 0.0
        try:
            eta_text = self._queue_table_item_text(int(row), 4)
            duration_text = self._queue_table_item_text(int(row), 3)
        except Exception:
            eta_text = ""
            duration_text = ""
        try:
            eta_text = str(self._queue_expected_time_label(int(row), eta_text, duration_text) or eta_text or duration_text)
        except Exception:
            eta_text = eta_text or duration_text
        parsed = self._parse_queue_seconds_value(eta_text)
        return max(0.0, float(parsed or 0.0))

    def queue_row_elapsed_seconds(self, row: int, now_ts: float | None = None) -> float:
        try:
            start_times = dict(getattr(self, "_file_start_times", {}) or {})
            complete_times = dict(getattr(self, "_file_complete_times", {}) or {})
            started_at = float(start_times.get(int(row), 0.0) or 0.0)
        except Exception:
            started_at = 0.0
            complete_times = {}
        if started_at <= 0.0:
            return 0.0
        try:
            ended_at = float(complete_times.get(int(row), 0.0) or 0.0)
        except Exception:
            ended_at = 0.0
        if ended_at <= 0.0:
            try:
                ended_at = float(now_ts if now_ts is not None else time.time())
            except Exception:
                ended_at = 0.0
        return max(0.0, ended_at - started_at)

    def _queue_row_started(self, row: int) -> bool:
        try:
            started_at = float((getattr(self, "_file_start_times", {}) or {}).get(int(row), 0.0) or 0.0)
        except Exception:
            return False
        return started_at > 0.0

    def _queue_row_elapsed_label(
        self,
        row: int,
        now_ts: float | None = None,
        *,
        allow_zero: bool = False,
    ) -> str | None:
        elapsed = self.queue_row_elapsed_seconds(row, now_ts=now_ts)
        if elapsed <= 0.0:
            if allow_zero and self._queue_row_started(row):
                return self._format_queue_clock(0.0)
            return None
        return self._format_queue_clock(elapsed)

    def _queue_eta_text_with_elapsed(
        self,
        row: int,
        expected_label,
        *,
        now_ts: float | None = None,
        include_elapsed: bool = False,
        allow_zero_elapsed: bool = False,
    ) -> str:
        label = str(expected_label or "예상불가")
        if include_elapsed:
            elapsed_label = self._queue_row_elapsed_label(
                row,
                now_ts=now_ts,
                allow_zero=allow_zero_elapsed,
            )
            if elapsed_label:
                return f"{elapsed_label} / {label}"
        return label

    def queue_row_metrics(self, row: int, *, now_ts: float | None = None) -> dict[str, object]:
        snapshot = self.queue_row_snapshot(row)
        state = self._queue_row_status_state(row)
        expected = self.queue_row_expected_seconds(row)
        elapsed = self.queue_row_elapsed_seconds(row, now_ts=now_ts)
        expected_label = self._queue_expected_time_label(
            row,
            str(snapshot.get("eta", "") or ""),
            str(snapshot.get("duration", "") or ""),
        ) or "예상불가"
        return {
            "row": int(snapshot.get("row", row) or row),
            "snapshot": snapshot,
            "status": str(state.get("status", "") or ""),
            "done": bool(state.get("done", False)),
            "error": bool(state.get("error", False)),
            "status_active": bool(state.get("status_active", False)),
            "started": bool(self._queue_row_started(row)),
            "expected": float(expected),
            "elapsed": float(elapsed),
            "expected_label": str(expected_label or "예상불가"),
        }

    def _queue_row_metrics_list(self, total_rows: int, *, now_ts: float | None = None) -> list[dict[str, object]]:
        return [self.queue_row_metrics(row, now_ts=now_ts) for row in range(max(0, int(total_rows)))]

    def _queue_done_reuse_counts_from_metrics(self, row_metrics: list[dict[str, object]]) -> tuple[int, int]:
        done_count = 0
        reuse_count = 0
        for metrics in list(row_metrics or []):
            status_text = str(metrics.get("status", "") or "")
            if not status_text:
                continue
            if "기존자막" in status_text:
                reuse_count += 1
            elif bool(metrics.get("done", False)):
                done_count += 1
        return done_count, reuse_count

    def _queue_completion_percent(self, *, total: int, done_count: int, reuse_count: int) -> int:
        if reuse_count >= total and total > 0:
            pct = 100
        else:
            effective_total = max(1, int(total) - int(reuse_count))
            pct = int((int(done_count) / effective_total) * 100)
        return max(0, min(100, pct))

    def queue_progress_metrics(self, *, now_ts: float | None = None, running: bool = False) -> dict[str, float | int | bool]:
        try:
            now_value = float(now_ts if now_ts is not None else time.time())
        except Exception:
            now_value = 0.0
        active_row = int(self.queue_active_row_index())
        row_count = int(self.queue_row_count())
        progress = self.queue_progress_state()
        total_files = max(row_count, int(progress["total"] or 0))
        total_expected = 0.0
        total_elapsed = 0.0
        progress_elapsed = 0.0
        known_expected_rows = 0
        all_done = total_files > 0
        row_metrics = self._queue_row_metrics_list(total_files, now_ts=now_value)
        done_count, reuse_count = self._queue_done_reuse_counts_from_metrics(row_metrics)
        completion_percent = self._queue_completion_percent(
            total=total_files,
            done_count=done_count,
            reuse_count=reuse_count,
        )

        for row, metrics in enumerate(row_metrics):
            row_done = bool(metrics["done"])
            row_error = bool(metrics["error"])
            expected = float(metrics["expected"])
            elapsed = float(metrics["elapsed"])
            if elapsed > 0.0:
                total_elapsed += elapsed
            if expected > 0.0:
                total_expected += expected
                known_expected_rows += 1
                if row_done:
                    progress_elapsed += expected
                elif row == active_row and running:
                    progress_elapsed += min(elapsed, expected)
            if not row_done and not row_error:
                all_done = False

        percent = float(progress["pct"] or 0.0)
        if total_expected > 0.0 and known_expected_rows >= total_files and total_files > 0:
            percent = (progress_elapsed / total_expected) * 100.0
        if all_done and total_files > 0:
            percent = 100.0
        elif running:
            percent = min(percent, 99.0)
        percent = max(0.0, min(100.0, percent))
        return {
            "active_row": active_row,
            "row_count": row_count,
            "total_files": total_files,
            "total_expected": float(total_expected),
            "total_elapsed": float(total_elapsed),
            "progress_elapsed": float(progress_elapsed),
            "known_expected_rows": int(known_expected_rows),
            "all_done": bool(all_done),
            "done_count": int(done_count),
            "reuse_count": int(reuse_count),
            "completion_percent": int(completion_percent),
            "percent": float(percent),
        }

    def queue_sidebar_items(self) -> list[dict]:
        table = self._queue_table_ref()
        cached_items = self._sidebar_queue_cache_items_copy()
        if table is None:
            return cached_items
        try:
            if self._queue_row_count() == 0:
                return []
            self._sync_all_queue_row_cache_from_table()
        except RuntimeError:
            return cached_items
        return self._queue_sidebar_items_from_cache()

    def _queue_sidebar_panel_ref(self):
        return getattr(self, "sidebar_queue_panel", None)

    def _queue_sidebar_panel_header(self) -> str:
        return self.queue_sidebar_header_text()

    def _queue_sidebar_panel_items(self) -> list[dict]:
        return self.queue_sidebar_items()

    def queue_sidebar_panel_payload(self) -> dict[str, object]:
        return {
            "header": self._queue_sidebar_panel_header(),
            "items": self._queue_sidebar_panel_items(),
        }

    def _apply_queue_sidebar_panel_payload(self, panel, payload: dict[str, object]) -> bool:
        if panel is None:
            return False
        data = dict(payload or {})
        setter = getattr(panel, "set_queue_payload", None)
        if callable(setter):
            setter(data)
            return True
        fallback = getattr(panel, "set_queue", None)
        if not callable(fallback):
            return False
        fallback(
            data.get("header", DEFAULT_QUEUE_HEADER),
            data.get("items", []),
        )
        return True

    def _clear_sidebar_queue_panel_ref(self) -> None:
        try:
            self.sidebar_queue_panel = None
        except Exception:
            return

    def sync_sidebar_queue_panel(self) -> bool:
        panel = self._queue_sidebar_panel_ref()
        if panel is None:
            return False
        payload = self.queue_sidebar_panel_payload()
        try:
            return bool(self._apply_queue_sidebar_panel_payload(panel, payload))
        except RuntimeError:
            self._clear_sidebar_queue_panel_ref()
            return False

    def _queue_probe_value_from_snapshot(self, snapshot: dict[str, object], col: int) -> str:
        col_idx = int(col)
        if col_idx == 0:
            value = snapshot.get("status", "")
        elif col_idx == 2:
            value = snapshot.get("info", "")
        elif col_idx == 4:
            value = snapshot.get("eta", "")
        else:
            value = ""
        return str(value or "")

    def _queue_probe_parts_from_snapshot(
        self,
        snapshot: dict[str, object],
        columns: tuple[int, ...] = (0, 2, 4),
    ) -> list[str]:
        parts: list[str] = []
        for col in tuple(columns or ()):
            value = self._queue_probe_value_from_snapshot(snapshot, int(col))
            if value:
                parts.append(value)
        return parts

    def queue_status_probe_parts(self, row: int = 0, columns: tuple[int, ...] = (0, 2, 4)) -> list[str]:
        try:
            row_idx = int(row)
        except Exception:
            row_idx = 0
        snapshot = self.queue_row_snapshot(row_idx)
        if not snapshot:
            return []
        return self._queue_probe_parts_from_snapshot(snapshot, tuple(columns or ()))

    def queue_completion_state(self) -> dict[str, int | bool]:
        row_count = int(self._queue_row_count())
        done_rows = 0
        error_rows = 0
        for row in self._queue_row_indices():
            state = self._queue_row_status_state(row)
            if state["done"]:
                done_rows += 1
            elif state["error"]:
                error_rows += 1
        return {
            "row_count": row_count,
            "done_rows": done_rows,
            "error_rows": error_rows,
            "all_done": bool(row_count > 0 and done_rows >= row_count),
        }

    def sync_saved_queue_state_for_media(self, media_path: str = "", current_row_hint=None) -> int | None:
        row = self.find_queue_row_for_media(
            media_path=media_path,
            current_row_hint=current_row_hint,
        )
        if row is None:
            return None
        self.update_queue_status(row, "✅ 완료", "", "", "")
        if self._queue_row_count() == 1:
            self.update_queue_header(1, 1, 100, "")
        else:
            self._refresh_queue_sidebar_views()
        return int(row)

    def _apply_queue_row_visual_state(self, row: int):
        try:
            row_idx = int(row)
        except Exception:
            return
        if row_idx < 0 or row_idx >= self._queue_row_count():
            return
        fg, bg = self._queue_row_visual_palette(row_idx)
        for item in self._queue_row_items(row_idx):
            item.setForeground(fg)
            item.setBackground(bg)

    def _mark_prior_queue_rows_done(self, current_one_based: int):
        row_count = self._queue_row_count()
        if row_count <= 0:
            return
        try:
            boundary = min(max(0, int(current_one_based) - 1), row_count)
        except Exception:
            return
        for row in range(boundary):
            state = self._queue_row_status_state(row)
            if state["error"]:
                self._apply_queue_row_visual_state(row)
                continue
            if not state["done"]:
                self._set_queue_row_status_text(row, "✅ 완료")
                if hasattr(self, "_file_complete_times"):
                    self._file_complete_times.setdefault(row, time.time())
            self._apply_queue_row_visual_state(row)

    def _animate_queue_status(self):
        self._queue_anim_idx = (self._queue_anim_idx + 1) % len(self._queue_anim_frames)
        for row in self._queue_row_indices():
            txt = self.queue_row_status_text(row)
            if "자막 생성 중" in txt and "완료" not in txt:
                self._set_queue_row_status_text(row, "자막 생성 중")
            elif "자막영상출력" in txt or "영상출력" in txt:
                self._set_queue_row_status_text(row, "자막영상출력(mov)")

    def init_queue_list(self, files):
        import os
        table = self._queue_table_ref()
        if table is None:
            return
        if hasattr(self, "_show_bottom_queue_table"):
            self._show_bottom_queue_table()
        self._current_file_idx = 1
        self._total_files = len(files)
        self._expected_seconds = {}
        self._file_start_times = {}
        self._file_complete_times = {}
        self._queue_execution_started_at = 0.0
        self._queue_row_cache = []
        self._real_pct = 0
        self._queue_state_model = QueueStateModel.empty("")
        if files:
            self._sidebar_queue_cache_items = []
            self._sidebar_queue_cache_header = ""
        self._accumulated_vad = []   # ← 멀티클립 VAD 누적 초기화

        table.setUpdatesEnabled(False)
        self._clear_queue_table_rows()

        active_row = 0 if files else -1
        self._queue_row_cache = []
        for i, f in enumerate(files):
            if not self._insert_queue_table_row(i):
                continue
            snapshot = self._populate_queue_table_row(
                i,
                status_text="대기 중",
                file_text=os.path.basename(f),
                info_text="분석 중..",
                duration_text="-",
                eta_text="계산 중",
            )
            self._set_queue_row_cache_entry(
                i,
                self._queue_sidebar_item_for_row(
                    i,
                    snapshot=snapshot,
                    active_row=active_row,
                )
            )

        table.setUpdatesEnabled(True)

        self._set_queue_header_text(format_queue_header(1 if files else 0, len(files), 0))
        self._queue_state_model = self._queue_state_model.with_header(
            format_queue_header(1 if files else 0, len(files), 0)
        )
        self._refresh_queue_sidebar_views()
        self._live_timer.start(1000)

    def _queue_backend_pipeline_started_at(self) -> float:
        started_values = []
        for backend_name in ("backend_fast", "backend"):
            backend = getattr(self, backend_name, None)
            if backend is None:
                continue
            try:
                started_at = float(getattr(backend, "pipeline_start_time", 0.0) or 0.0)
            except Exception:
                continue
            if started_at > 0.0:
                started_values.append(started_at)
        return min(started_values) if started_values else 0.0

    def _queue_execution_started_at_value(self) -> float:
        try:
            explicit_started_at = float(getattr(self, "_queue_execution_started_at", 0.0) or 0.0)
        except Exception:
            explicit_started_at = 0.0
        if explicit_started_at > 0.0:
            return explicit_started_at
        return self._queue_backend_pipeline_started_at()

    def _queue_execution_started(self) -> bool:
        return self._queue_execution_started_at_value() > 0.0

    def mark_queue_execution_started(self, now_ts: float | None = None) -> None:
        try:
            started_at = float(now_ts if now_ts is not None else time.time())
        except Exception:
            started_at = time.time()
        self._queue_execution_started_at = max(0.0, started_at)

    def _queue_mark_row_started(self, idx: int, *, incoming_active: bool, now_ts: float | None = None) -> None:
        if not incoming_active or idx in self._file_start_times:
            return
        if not self._queue_execution_started():
            return
        status_text = self._queue_table_item_text(idx, 0)
        if not self._queue_elapsed_tracking_active(status_text):
            return
        try:
            started_at = float(now_ts if now_ts is not None else time.time())
        except Exception:
            started_at = time.time()
        self._file_start_times[idx] = started_at

    def _queue_status_tracks_elapsed(self, status_text: str) -> bool:
        text = str(status_text or "").strip()
        if not text:
            return False
        if is_generation_stage_status(text):
            return True
        lowered = text.lower()
        if "재시작 준비 중" in text or "시작 준비 중" in text:
            return True
        if "러프컷" in text and ("llm" in lowered or "후처리" in text):
            return True
        return False

    def _queue_elapsed_tracking_active(self, status_text: str = "") -> bool:
        if self._queue_status_tracks_elapsed(status_text):
            return True

        running_checker = getattr(self, "_is_subtitle_generation_running", None)
        if callable(running_checker):
            try:
                if bool(running_checker()):
                    return True
            except (RuntimeError, AttributeError, TypeError) as exc:
                self._queue_log_nonfatal("generation running probe", exc)

        editor = getattr(self, "_editor_widget", None)
        if editor is not None:
            if bool(getattr(editor, "_roughcut_draft_pending", False)):
                return True
            cleanup_pending = getattr(editor, "_roughcut_draft_cleanup_pending", None)
            if callable(cleanup_pending):
                try:
                    if bool(cleanup_pending()):
                        return True
                except (RuntimeError, AttributeError, TypeError) as exc:
                    self._queue_log_nonfatal("roughcut cleanup probe", exc)
            state_manager = getattr(editor, "sm", None)
            if state_manager is not None:
                if str(getattr(state_manager, "state", "") or "") == "ST_PROC":
                    return True
                if bool(getattr(state_manager, "is_locked", False)):
                    return True
            if bool(getattr(editor, "_is_ai_processing", False)):
                return True

        for backend_name in ("backend_fast", "backend"):
            backend = getattr(self, backend_name, None)
            if backend is None:
                continue
            for attr in ("_active", "is_running", "running"):
                value = getattr(backend, attr, False)
                if callable(value):
                    try:
                        value = value()
                    except Exception:
                        value = False
                if bool(value):
                    return True
        return False

    def _queue_record_completed_row(self, idx: int, *, now_ts: float | None = None) -> None:
        try:
            completed_at = float(now_ts if now_ts is not None else time.time())
        except Exception:
            completed_at = time.time()
        self._file_complete_times[idx] = completed_at
        expected_label = self._queue_expected_time_label(
            idx,
            self._queue_table_item_text(idx, 4),
            self._queue_table_item_text(idx, 3),
        ) or "?"
        eta_text = self._queue_eta_text_with_elapsed(
            idx,
            expected_label,
            now_ts=completed_at,
            include_elapsed=True,
        )
        if "/" in eta_text:
            self._set_queue_table_item_text(idx, 4, eta_text)
        self._finalize_queue_if_all_rows_done()

    def _queue_apply_expected_time_text(
        self,
        idx: int,
        time_txt,
        *,
        incoming_active: bool,
        now_ts: float | None = None,
    ) -> None:
        if not time_txt or idx in self._file_complete_times:
            return
        sec_val = self._parse_queue_seconds_value(time_txt)
        if sec_val is not None and sec_val > 0:
            self._expected_seconds[idx] = sec_val
            expected_label = self._format_queue_clock(sec_val)
            self._set_queue_table_item_text(
                idx,
                4,
                self._queue_eta_text_with_elapsed(
                    idx,
                    expected_label,
                    now_ts=now_ts,
                    include_elapsed=bool(incoming_active and idx in self._file_start_times),
                    allow_zero_elapsed=True,
                ),
            )
            return
        expected_label = (
            self._queue_expected_display_text(time_txt)
            if self._queue_expected_time_is_unknown(time_txt)
            else str(time_txt)
        )
        self._set_queue_table_item_text(
            idx,
            4,
            self._queue_eta_text_with_elapsed(
                idx,
                expected_label,
                now_ts=now_ts,
                include_elapsed=bool(incoming_active and idx in self._file_start_times),
                allow_zero_elapsed=True,
            ),
        )

    def _queue_apply_row_status_text(
        self,
        idx: int,
        status_text,
        *,
        incoming_active: bool,
        now_ts: float | None = None,
    ) -> bool:
        apply_status = str(status_text or "")
        if not apply_status:
            return False
        self._sync_editor_stage_from_queue_status(apply_status)
        self._set_queue_table_item_text(idx, 0, apply_status)
        self._queue_mark_row_started(idx, incoming_active=incoming_active, now_ts=now_ts)
        if self._queue_status_flags(apply_status)[0]:
            self._queue_record_completed_row(idx, now_ts=now_ts)
        return True

    def _queue_skip_row_update(self, idx: int, *, refresh_engine: bool = True) -> None:
        self._apply_queue_row_visual_state(idx)
        self._refresh_queue_sidebar_views()
        if refresh_engine and hasattr(self, "_refresh_sidebar_engine_info"):
            self._refresh_sidebar_engine_info()

    def _queue_existing_row_update_policy(
        self,
        idx: int,
        *,
        current_status: str,
        incoming_status: str,
        incoming_done: bool,
        incoming_error: bool,
    ) -> dict[str, object]:
        current_done, current_error, current_active = self._queue_status_flags(current_status)
        if current_done and not incoming_done:
            restart = self._queue_status_restarts_completed_row(idx, incoming_status)
            followup = self._queue_status_reopens_completed_row_for_followup(incoming_status)
            if restart or followup:
                self._reset_completed_queue_row_for_restart(
                    idx,
                    preserve_start_time=followup,
                    preserve_progress=followup,
                )
                current_done = False
            else:
                return {
                    "skip": True,
                    "current_done": True,
                    "current_error": current_error,
                    "current_active": current_active,
                }
        if current_error and not (incoming_error or incoming_done):
            return {
                "skip": True,
                "current_done": current_done,
                "current_error": True,
                "current_active": current_active,
            }
        return {
            "skip": False,
            "current_done": current_done,
            "current_error": current_error,
            "current_active": current_active,
        }

    def _queue_status_text_for_row_update(
        self,
        status_text,
        *,
        current_active: bool,
        incoming_done: bool,
        incoming_error: bool,
        incoming_active: bool,
    ) -> str:
        apply_status = str(status_text or "")
        if current_active and not (incoming_done or incoming_error or incoming_active):
            return ""
        return apply_status

    def update_queue_status(self, idx, status=None, time_txt="", info_txt="", len_txt=""):
        payload = normalize_queue_status_payload(idx, status, time_txt, info_txt, len_txt)
        idx = int(payload["idx"])
        status = payload["status"]
        time_txt = payload["time_txt"]
        info_txt = payload["info_txt"]
        len_txt = payload["len_txt"]
        if hasattr(self, "_show_bottom_queue_table") and status:
            self._show_bottom_queue_table()
        engine_dirty = False
        table = self._queue_table_ref()
        if table is not None and 0 <= idx < self._queue_row_count():
            now_ts = time.time()
            incoming_done, incoming_error, incoming_active = self._queue_status_flags(status)
            try:
                current_idx = int(getattr(self, "_current_file_idx", 0) or 0)
            except Exception:
                current_idx = 0
            if (incoming_done or incoming_error or incoming_active) and idx + 1 > current_idx:
                self._current_file_idx = idx + 1
            if idx > 0 and (incoming_done or incoming_error or incoming_active):
                self._mark_prior_queue_rows_done(idx + 1)
            current_status = self._queue_table_item_text(idx, 0)
            row_policy = self._queue_existing_row_update_policy(
                idx,
                current_status=current_status,
                incoming_status=status,
                incoming_done=incoming_done,
                incoming_error=incoming_error,
            )
            current_active = bool(row_policy["current_active"])
            if bool(row_policy["skip"]):
                self._queue_skip_row_update(idx)
                return
            apply_status = self._queue_status_text_for_row_update(
                status,
                current_active=current_active,
                incoming_done=incoming_done,
                incoming_error=incoming_error,
                incoming_active=incoming_active,
            )
            engine_dirty = self._queue_apply_row_status_text(
                idx,
                apply_status,
                incoming_active=incoming_active,
                now_ts=now_ts,
            )
            if info_txt:
                self._set_queue_table_item_text(idx, 2, info_txt)
            if len_txt:
                self._set_queue_table_item_text(idx, 3, len_txt)
            self._queue_apply_expected_time_text(
                idx,
                time_txt,
                incoming_active=incoming_active,
                now_ts=now_ts,
            )
            self._apply_queue_row_visual_state(idx)
            self._sync_queue_row_cache_from_table_row(idx)
            self._sync_all_queue_row_cache_from_table()
        self._refresh_queue_sidebar_views()
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
            except (RuntimeError, AttributeError, TypeError) as exc:
                self._queue_log_nonfatal("cut boundary status sync", exc)
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
                    except (RuntimeError, AttributeError, TypeError) as exc:
                        self._queue_log_nonfatal("editor completion status sync", exc)
                else:
                    try:
                        state_manager.complete_auto_mode() if bool(getattr(editor, "is_auto_start", False)) else state_manager.complete_ai()
                    except (RuntimeError, AttributeError, TypeError) as exc:
                        self._queue_log_nonfatal("state-manager completion sync", exc)
            clearer = getattr(editor, "_clear_processing_indicators", None)
            if callable(clearer):
                try:
                    clearer()
                except (RuntimeError, AttributeError, TypeError) as exc:
                    self._queue_log_nonfatal("processing indicator cleanup", exc)
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

    def _finalize_queue_if_all_rows_done(self):
        row_count = self._queue_row_count()
        if row_count <= 0:
            return
        row_statuses = self._queue_row_statuses()
        if not row_statuses or not all(self._queue_status_flags(st)[0] for st in row_statuses):
            return
        total = int(getattr(self, "_total_files", row_count) or row_count)
        self._current_file_idx = total
        self._real_pct = 100
        if hasattr(self, "_live_timer"):
            self._live_timer.stop()
        self._set_queue_header_text(format_queue_header(total, total, 100))
        self._sync_all_queue_row_cache_from_table()

    def _refresh_active_queue_elapsed(self, now: float | None = None) -> bool:
        table = self._queue_table_ref()
        if table is None:
            return False
        active_row = self._current_queue_active_row()
        if active_row < 0:
            return False
        try:
            now_value = float(now if now is not None else time.time())
            metrics = self.queue_row_metrics(active_row, now_ts=now_value)
            if bool(metrics["done"]) or not bool(metrics["status_active"]):
                return False
            if active_row not in self._file_start_times and not self._queue_execution_started():
                return False
            if not self._queue_elapsed_tracking_active(str(metrics.get("status", "") or "")):
                return False
            if active_row not in self._file_start_times:
                started_at = self._queue_execution_started_at_value()
                self._file_start_times[active_row] = started_at if started_at > 0.0 else now_value
            self._set_queue_table_item_text(
                active_row,
                4,
                self._queue_eta_text_with_elapsed(
                    active_row,
                    metrics["expected_label"],
                    now_ts=now_value,
                    include_elapsed=True,
                    allow_zero_elapsed=True,
                ),
            )
            self._apply_queue_row_visual_state(active_row)
            self._sync_queue_row_cache_from_table_row(active_row)
            return True
        except Exception:
            return False

    def _queue_live_header_percent(
        self,
        *,
        total: int,
        row_statuses: list[str] | None = None,
        now_ts: float | None = None,
    ) -> int:
        metrics_getter = getattr(self, "queue_progress_metrics", None)
        if callable(metrics_getter):
            try:
                metrics = dict(metrics_getter(now_ts=now_ts, running=True) or {})
                total_expected = float(metrics.get("total_expected", 0.0) or 0.0)
                known_expected_rows = int(metrics.get("known_expected_rows", 0) or 0)
                total_files = max(0, int(metrics.get("total_files", total) or total))
                if total_expected > 0.0 and known_expected_rows >= total_files and total_files > 0:
                    return max(0, min(100, int(round(float(metrics.get("percent", 0.0) or 0.0)))))
            except (RuntimeError, AttributeError, TypeError, ValueError) as exc:
                self._queue_log_nonfatal("live header percent", exc)
        statuses = list(row_statuses if row_statuses is not None else self._queue_row_statuses())
        row_metrics = [
            {"status": status_text, "done": bool(self._queue_status_flags(status_text)[0])}
            for status_text in statuses
        ]
        done_count, reuse_count = self._queue_done_reuse_counts_from_metrics(row_metrics)
        return self._queue_completion_percent(
            total=total,
            done_count=done_count,
            reuse_count=reuse_count,
        )

    def _queue_apply_done_row_visuals(self, row_statuses: list[str] | None = None) -> None:
        statuses = list(row_statuses if row_statuses is not None else self._queue_row_statuses())
        for row, status_text in enumerate(statuses):
            if not status_text:
                continue
            row_done, _row_error, _status_active = self._queue_status_flags(status_text)
            if row_done:
                self._apply_queue_row_visual_state(row)

    def _update_live_queue_header(self):
        table = self._queue_table_ref()
        if table is None:
            return
        active_backend = None
        if getattr(self, 'backend_fast', None) and getattr(self.backend_fast, '_active', False):
            active_backend = self.backend_fast
        elif self.backend and getattr(self.backend, '_active', False):
            active_backend = self.backend
        if not active_backend and not self._refresh_active_queue_elapsed():
            return
        if active_backend and getattr(active_backend, 'pipeline_start_time', 0) == 0:
            return

        now = time.time()
        c = getattr(self, '_current_file_idx', 1)
        t = getattr(self, '_total_files', 1)
        self._mark_prior_queue_rows_done(c)
        row_statuses = self._queue_row_statuses()
        pct = self._queue_live_header_percent(total=t, row_statuses=row_statuses, now_ts=now)
        self._set_queue_header_text(format_queue_header(c, t, pct))
        self._queue_apply_done_row_visuals(row_statuses=row_statuses)
        self._refresh_active_queue_elapsed(now)
        self._refresh_queue_sidebar_views()
        if hasattr(self, "_refresh_sidebar_engine_info"):
            self._refresh_sidebar_engine_info()

    def _queue_row_statuses(self) -> list[str]:
        return [self.queue_row_status_text(row) for row in self._queue_row_indices()]

    def _queue_header_restart_reset_allowed(
        self,
        *,
        prev_pct: int,
        pct: int,
        current: int,
        prev_current: int,
    ) -> bool:
        if prev_pct < 100 or pct > 0 or current > max(prev_current, 1):
            return False
        try:
            row_count = self._queue_row_count()
            active_row = max(0, min(row_count - 1, current - 1))
            status_text = self._queue_table_item_text(active_row, 0)
            row_done, row_error, row_active = self._queue_status_flags(status_text)
            return not row_done and not row_error and (row_active or "대기" in status_text)
        except Exception:
            return False

    def _queue_header_effective_pct(
        self,
        *,
        pct: int,
        prev_pct: int,
        current: int,
        prev_current: int,
        total: int,
        row_statuses: list[str],
    ) -> int:
        final_signal = pct >= 100 and total > 0 and current >= total
        allow_restart_reset = self._queue_header_restart_reset_allowed(
            prev_pct=prev_pct,
            pct=pct,
            current=current,
            prev_current=prev_current,
        )
        if not final_signal and pct < prev_pct and current <= max(prev_current, 1) and not allow_restart_reset:
            pct = prev_pct
        all_rows_done = bool(row_statuses) and all(self._queue_status_flags(st)[0] for st in row_statuses)
        if pct == 100 and row_statuses and not all_rows_done:
            pct = 0 if all("대기" in st for st in row_statuses) else min(99, max(0, int(pct)))
        return int(pct)

    def _queue_finalize_header_completion(self, *, total: int) -> None:
        for row in self._queue_row_indices():
            status_text = self.queue_row_status_text(row)
            if any(token in status_text for token in ("오류", "실패", "중단")):
                continue
            done_text = "✅기존자막" if "기존자막" in status_text else "✅ 완료"
            self._set_queue_row_status_text(row, done_text)
            self._apply_queue_row_visual_state(row)
        if hasattr(self, '_live_timer'):
            self._live_timer.stop()
        self._set_queue_header_text(format_queue_header(total, total, 100))

    def update_queue_header(self, current, total=None, pct=None, eta_str=""):
        payload = normalize_queue_header_payload(current, total, pct, eta_str)
        current = payload["current"]
        total = payload["total"]
        pct = payload["pct"]
        eta_str = payload["eta_str"]
        table = self._queue_table_ref()
        if table is None:
            return
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
        self._current_file_idx = current
        self._total_files = total
        self._mark_prior_queue_rows_done(current)
        try:
            row_statuses = self._queue_row_statuses()
        except Exception:
            row_statuses = []
        pct = self._queue_header_effective_pct(
            pct=pct,
            prev_pct=prev_pct,
            current=current,
            prev_current=prev_current,
            total=total,
            row_statuses=row_statuses,
        )
        all_rows_done = bool(row_statuses) and all(self._queue_status_flags(st)[0] for st in row_statuses)
        self._real_pct = pct
        if pct == 100 and all_rows_done:
            self._queue_finalize_header_completion(total=total)
        else:
            self._set_queue_header_text(format_queue_header(current, total, pct))
        state_model = getattr(self, "_queue_state_model", None)
        if isinstance(state_model, QueueStateModel):
            self._queue_state_model = state_model.with_header(format_queue_header(current, total, pct))
        self._sync_all_queue_row_cache_from_table()
        self._refresh_queue_sidebar_views()
        if hasattr(self, "_refresh_sidebar_engine_info"):
            self._refresh_sidebar_engine_info()

    def _refresh_sidebar_queue_cache(self):
        self._sync_all_queue_row_cache_from_table()
        items = self._queue_sidebar_items_from_cache()
        if items or not self._sidebar_queue_cache_items_copy():
            self._sidebar_queue_cache_items = items
        try:
            header = str(self.queue_sidebar_header_text() or "")
        except RuntimeError:
            header = ""
        self._sidebar_queue_cache_header = header

    def _sync_queue_row_cache_from_table_row(self, row: int) -> None:
        table = self._queue_table_ref()
        if table is None or row < 0:
            return
        try:
            if row >= self._queue_row_count():
                return
            active_row = self._current_queue_active_row()
            entry = self._queue_sidebar_item_for_row(row, active_row=active_row)
            self._set_queue_row_cache_entry(row, entry)
        except RuntimeError:
            return

    def _sync_all_queue_row_cache_from_table(self) -> None:
        table = self._queue_table_ref()
        if table is None:
            return
        try:
            active_row = self._current_queue_active_row()
            self._queue_row_cache = [
                self._queue_sidebar_item_for_row(row, active_row=active_row)
                for row in self._queue_row_indices()
            ]
            self._queue_state_model = QueueStateModel.from_snapshots(
                [self.queue_row_snapshot(row) for row in self._queue_row_indices()],
                header=str(getattr(self, "_sidebar_queue_cache_header", "") or self.queue_sidebar_header_text()),
            )
        except RuntimeError:
            return
