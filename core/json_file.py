from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
from typing import Any

from core.native_json import dumps_json_bytes, loads_json


_JSON_FILE_LOCK = threading.RLock()


def _log(message: str) -> None:
    try:
        from core.runtime.logger import get_logger

        get_logger().log(message)
    except Exception:
        pass


def _backup_path(path: str) -> str:
    return f"{path}.bak"


def _corrupt_path(path: str) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return f"{path}.corrupt.{stamp}"


def _matches_type(value: Any, expected_type: type | tuple[type, ...] | None) -> bool:
    return expected_type is None or isinstance(value, expected_type)


def read_json_file(
    path: str,
    *,
    default: Any = None,
    expected_type: type | tuple[type, ...] | None = None,
    context: str = "JSON",
    restore_backup: bool = True,
    log_errors: bool = True,
) -> Any:
    path = str(path or "")
    try:
        with open(path, "rb") as handle:
            data = loads_json(handle.read())
        if _matches_type(data, expected_type):
            return data
        if log_errors:
            _log(f"⚠️ {context} 형식 오류: {os.path.basename(path)}")
        return default
    except FileNotFoundError:
        return default
    except Exception as exc:
        if log_errors:
            _log(f"⚠️ {context} 로드 실패: {exc}")

    if restore_backup:
        backup = _backup_path(path)
        try:
            with open(backup, "rb") as handle:
                data = loads_json(handle.read())
            if _matches_type(data, expected_type):
                write_json_file_atomic(path, data, backup=False)
                if log_errors:
                    _log(f"♻️ {context} 백업 복구 완료: {os.path.basename(path)}")
                return data
        except Exception:
            pass

    try:
        if path and os.path.exists(path):
            shutil.copy2(path, _corrupt_path(path))
    except Exception:
        pass
    return default


def write_json_file_atomic(path: str, data: Any, *, indent: int | None = 2, backup: bool = True) -> None:
    path = str(path or "")
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    tmp_path = ""
    with _JSON_FILE_LOCK:
        try:
            with tempfile.NamedTemporaryFile("wb", dir=directory, prefix=".tmp-", suffix=".json", delete=False) as handle:
                tmp_path = handle.name
                handle.write(dumps_json_bytes(data, indent=indent, append_newline=True))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
            if backup:
                try:
                    shutil.copy2(path, _backup_path(path))
                except Exception:
                    pass
        finally:
            if tmp_path:
                try:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                except Exception:
                    pass
