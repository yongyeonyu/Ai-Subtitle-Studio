"""Optional native JSON helpers.

`orjson` is a Rust extension module. When it is available we use it for the
large settings/cache/project-adjacent JSON paths; otherwise the standard
library keeps the exact same behavior.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import IO
from typing import Any

try:
    import orjson  # type: ignore
except Exception:  # pragma: no cover - exercised by fallback environments.
    orjson = None  # type: ignore


HAS_NATIVE_JSON = orjson is not None


def native_json_enabled() -> bool:
    if orjson is None:
        return False
    return _native_json_env_enabled(os.environ.get("AI_SUBTITLE_NATIVE_JSON", "1"))


@lru_cache(maxsize=8)
def _native_json_env_enabled(raw_value: str | None) -> bool:
    value = str(raw_value or "1").strip().lower()
    return value not in {"0", "false", "off", "no"}


def json_default(value: Any) -> Any:
    if isinstance(value, (set, tuple)):
        return list(value)
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except Exception:
            return str(value)
    return str(value)


def loads_json(data: str | bytes | bytearray) -> Any:
    if native_json_enabled():
        return orjson.loads(data)
    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8")
    return json.loads(data)


def loads_json_output(data: str | bytes | bytearray | None, *, default: Any = None) -> Any:
    if data is None or data == "" or data == b"" or (isinstance(data, bytearray) and not data):
        return {} if default is None else default
    return loads_json(data)


@lru_cache(maxsize=16)
def _orjson_dump_options(indent: int | None, sort_keys: bool, append_newline: bool) -> int:
    option = orjson.OPT_NON_STR_KEYS
    if indent == 2:
        option |= orjson.OPT_INDENT_2
    if sort_keys:
        option |= orjson.OPT_SORT_KEYS
    if append_newline:
        option |= orjson.OPT_APPEND_NEWLINE
    return option


def dumps_json_bytes(
    data: Any,
    *,
    indent: int | None = None,
    sort_keys: bool = False,
    append_newline: bool = False,
    compact: bool = False,
    default: Any = None,
) -> bytes:
    if native_json_enabled() and indent in (None, 2):
        option = _orjson_dump_options(indent, bool(sort_keys), bool(append_newline))
        return orjson.dumps(data, option=option, default=default)

    separators = (",", ":") if compact and indent is None else None
    text = json.dumps(
        data,
        ensure_ascii=False,
        indent=indent,
        sort_keys=sort_keys,
        separators=separators,
        default=default,
    )
    if append_newline:
        text += "\n"
    return text.encode("utf-8")


def dumps_json_text(
    data: Any,
    *,
    indent: int | None = None,
    sort_keys: bool = False,
    append_newline: bool = False,
    compact: bool = False,
    default: Any = None,
) -> str:
    return dumps_json_bytes(
        data,
        indent=indent,
        sort_keys=sort_keys,
        append_newline=append_newline,
        compact=compact,
        default=default,
    ).decode("utf-8")


def read_json_path(path: str | Path) -> Any:
    return loads_json(Path(path).read_bytes())


def write_jsonl_line(stream: IO[str], text: str) -> None:
    stream.write(text)
    stream.write("\n")
