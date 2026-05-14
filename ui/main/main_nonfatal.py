from __future__ import annotations

from core.runtime.logger import get_logger


def is_deleted_qt_runtime_error(exc: BaseException) -> bool:
    text = str(exc or "")
    return "wrapped C/C++ object" in text and "has been deleted" in text


def log_nonfatal_ui_step(prefix: str, step: str, exc: BaseException, *, ignore_deleted_qt: bool = True) -> None:
    if ignore_deleted_qt and is_deleted_qt_runtime_error(exc):
        return
    try:
        get_logger().log(f"⚠️ {prefix} 실패 [{step}]: {exc}")
    except Exception:
        pass


def run_nonfatal_ui_step(
    prefix: str,
    step: str,
    callback,
    *,
    default=None,
    ignore_deleted_qt: bool = True,
):
    try:
        return callback()
    except RuntimeError as exc:
        if ignore_deleted_qt and is_deleted_qt_runtime_error(exc):
            return default
        log_nonfatal_ui_step(prefix, step, exc, ignore_deleted_qt=ignore_deleted_qt)
        return default
    except Exception as exc:
        log_nonfatal_ui_step(prefix, step, exc, ignore_deleted_qt=ignore_deleted_qt)
        return default


def call_nonfatal_ui_step(
    prefix: str,
    target,
    attr: str,
    *args,
    step: str | None = None,
    default=None,
    ignore_deleted_qt: bool = True,
    **kwargs,
):
    fn = getattr(target, attr, None) if target is not None else None
    if not callable(fn):
        return default
    return run_nonfatal_ui_step(
        prefix,
        step or attr,
        lambda: fn(*args, **kwargs),
        default=default,
        ignore_deleted_qt=ignore_deleted_qt,
    )
