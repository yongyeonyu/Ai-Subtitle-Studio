from __future__ import annotations

import os
from typing import Any

from ui.queue.queue_formatting import (
    build_queue_header_payload,
    build_queue_status_payload,
    normalize_queue_header_payload,
    normalize_queue_status_payload,
)


def dispatch_queue_status(
    target: Any,
    payload_or_idx: Any,
    status: Any = None,
    time_txt: Any = "",
    info_txt: Any = "",
    len_txt: Any = "",
) -> bool:
    payload = normalize_queue_status_payload(payload_or_idx, status, time_txt, info_txt, len_txt)
    signal = getattr(target, "_sig_update_queue_payload", None)
    if signal is not None:
        try:
            signal.emit(payload)
            return True
        except RuntimeError:
            return False
    updater = getattr(target, "update_queue_status", None)
    if callable(updater):
        updater(payload)
        return True
    return False


def dispatch_queue_header(
    target: Any,
    payload_or_current: Any,
    total: Any = None,
    pct: Any = None,
    eta_str: Any = "",
) -> bool:
    payload = normalize_queue_header_payload(payload_or_current, total, pct, eta_str)
    signal = getattr(target, "_sig_update_queue_header_payload", None)
    if signal is not None:
        try:
            signal.emit(payload)
            return True
        except RuntimeError:
            return False
    updater = getattr(target, "update_queue_header", None)
    if callable(updater):
        updater(payload)
        return True
    return False


def find_queue_row_for_media(
    main_window: Any,
    *,
    media_path: Any = "",
    current_row_hint: Any = None,
) -> int | None:
    finder = getattr(main_window, "find_queue_row_for_media", None)
    if callable(finder):
        return finder(
            media_path=str(media_path or ""),
            current_row_hint=current_row_hint,
        )
    table = getattr(main_window, "queue_table", None)
    if table is None:
        return None
    try:
        row_count = int(table.rowCount())
    except Exception:
        return None
    if row_count <= 0:
        return None

    candidates: list[int] = []
    hint = current_row_hint
    if hint is None:
        try:
            hint = int(getattr(main_window, "_current_file_idx", 1) or 1) - 1
        except Exception:
            hint = None
    try:
        if hint is not None:
            hint_idx = int(hint)
            if 0 <= hint_idx < row_count:
                candidates.append(hint_idx)
    except Exception:
        pass

    media_name = os.path.basename(str(media_path or "")).strip().lower()
    if media_name:
        for row in range(row_count):
            item = table.item(row, 1)
            item_name = os.path.basename(str(item.text() if item else "")).strip().lower()
            if item_name == media_name and row not in candidates:
                candidates.append(row)

    if not candidates and row_count == 1:
        return 0

    for row in candidates:
        try:
            status_item = table.item(row, 0)
            status_text = str(status_item.text() if status_item else "")
            if "완료" not in status_text and "기존자막" not in status_text:
                return row
        except Exception:
            continue
    return candidates[0] if candidates else None


def queue_active_row_index(target: Any) -> int:
    getter = getattr(target, "queue_active_row_index", None)
    if callable(getter):
        try:
            return int(getter())
        except Exception:
            return -1
    try:
        return max(0, int(getattr(target, "_current_file_idx", 1) or 1) - 1)
    except Exception:
        return 0


def queue_progress_state(
    target: Any,
    *,
    current_default: int = 0,
    total_default: int = 0,
    pct_default: int = 0,
) -> dict[str, int]:
    getter = getattr(target, "queue_progress_state", None)
    if callable(getter):
        try:
            payload = dict(getter() or {})
            return {
                "current": max(0, int(payload.get("current", current_default) or current_default)),
                "total": max(0, int(payload.get("total", total_default) or total_default)),
                "pct": max(0, int(payload.get("pct", pct_default) or pct_default)),
            }
        except Exception:
            pass
    try:
        current = max(0, int(getattr(target, "_current_file_idx", current_default) or current_default))
    except Exception:
        current = max(0, int(current_default))
    try:
        total = max(0, int(getattr(target, "_total_files", total_default) or total_default))
    except Exception:
        total = max(0, int(total_default))
    try:
        pct = max(0, int(getattr(target, "_real_pct", pct_default) or pct_default))
    except Exception:
        pct = max(0, int(pct_default))
    return {"current": current, "total": total, "pct": pct}


def sync_saved_queue_state(
    main_window: Any,
    *,
    media_path: Any = "",
    current_row_hint: Any = None,
) -> int | None:
    syncer = getattr(main_window, "sync_saved_queue_state_for_media", None)
    if callable(syncer):
        return syncer(
            media_path=str(media_path or ""),
            current_row_hint=current_row_hint,
        )
    row = find_queue_row_for_media(
        main_window,
        media_path=media_path,
        current_row_hint=current_row_hint,
    )
    if row is None:
        return None

    dispatch_queue_status(main_window, build_queue_status_payload(int(row), "✅ 완료", "", "", ""))
    table = getattr(main_window, "queue_table", None)
    try:
        row_count = int(table.rowCount()) if table is not None else 0
    except Exception:
        row_count = 0
    if row_count == 1:
        dispatch_queue_header(main_window, build_queue_header_payload(1, 1, 100, ""))
    else:
        refresher = getattr(main_window, "refresh_queue_views", None)
        if callable(refresher):
            refresher()
        elif hasattr(main_window, "_refresh_sidebar_queue_cache"):
            main_window._refresh_sidebar_queue_cache()
            if hasattr(main_window, "_sync_sidebar_queue_panel"):
                main_window._sync_sidebar_queue_panel()
    return int(row)
