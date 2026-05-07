from __future__ import annotations

"""Optional native JSON helpers.

`orjson` is a Rust extension module. When it is available we use it for the
large settings/cache/project-adjacent JSON paths; otherwise the standard
library keeps the exact same behavior.
"""

import json
import os
from pathlib import Path
from typing import Any

try:
    import orjson  # type: ignore
except Exception:  # pragma: no cover - exercised by fallback environments.
    orjson = None  # type: ignore


HAS_NATIVE_JSON = orjson is not None


def native_json_enabled() -> bool:
    if orjson is None:
        return False
    value = str(os.environ.get("AI_SUBTITLE_NATIVE_JSON", "1") or "1").strip().lower()
    return value not in {"0", "false", "off", "no"}


def loads_json(data: str | bytes | bytearray) -> Any:
    if native_json_enabled():
        return orjson.loads(data)
    if isinstance(data, (bytes, bytearray)):
        data = bytes(data).decode("utf-8")
    return json.loads(data)


def dumps_json_bytes(
    data: Any,
    *,
    indent: int | None = None,
    sort_keys: bool = False,
    append_newline: bool = False,
) -> bytes:
    if native_json_enabled() and indent in (None, 2):
        option = orjson.OPT_NON_STR_KEYS
        if indent == 2:
            option |= orjson.OPT_INDENT_2
        if sort_keys:
            option |= orjson.OPT_SORT_KEYS
        if append_newline:
            option |= orjson.OPT_APPEND_NEWLINE
        return orjson.dumps(data, option=option)

    text = json.dumps(data, ensure_ascii=False, indent=indent, sort_keys=sort_keys)
    if append_newline:
        text += "\n"
    return text.encode("utf-8")


def dumps_json_text(
    data: Any,
    *,
    indent: int | None = None,
    sort_keys: bool = False,
    append_newline: bool = False,
) -> str:
    return dumps_json_bytes(
        data,
        indent=indent,
        sort_keys=sort_keys,
        append_newline=append_newline,
    ).decode("utf-8")


def read_json_path(path: str | Path) -> Any:
    return loads_json(Path(path).read_bytes())
