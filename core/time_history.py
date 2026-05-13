"""Compatibility wrappers for the runtime ETA estimator."""

from core.runtime_eta import (
    ETA_HISTORY_SCHEMA,
    add_history,
    build_runtime_eta_payload,
    get_expected_time,
    history_store_path,
)

__all__ = [
    "ETA_HISTORY_SCHEMA",
    "add_history",
    "build_runtime_eta_payload",
    "get_expected_time",
    "history_store_path",
]
