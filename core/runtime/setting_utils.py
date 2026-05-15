"""Shared helpers for boolean-like settings and environment flags."""

from __future__ import annotations

import os
from typing import Any, Iterable

from core.coerce import positive_int


DEFAULT_TRUE_VALUES = frozenset({"1", "true", "on", "yes", "enabled", "enable", "사용", "켜짐", "켬"})
DEFAULT_FALSE_VALUES = frozenset({"0", "false", "off", "no", "disabled", "disable", "끄기", "끔"})
KOREAN_FALSE_VALUES = frozenset({"0", "false", "off", "no", "사용 안함", "사용안함", "미사용", "끔"})
ENV_TRUE_VALUES = frozenset({"1", "true", "on", "yes"})
ENV_FALSE_VALUES = frozenset({"0", "false", "off", "no"})


def _normalized_text(value: Any) -> str:
    return "" if value is None else str(value).strip().casefold()


def _normalized_tokens(values: Iterable[str]) -> frozenset[str]:
    if isinstance(values, frozenset):
        return values
    return frozenset(_normalized_text(item) for item in values)


def setting_bool(
    value: Any,
    default: bool = True,
    *,
    true_values: Iterable[str] = DEFAULT_TRUE_VALUES,
    false_values: Iterable[str] = DEFAULT_FALSE_VALUES,
    false_only_strings: bool = False,
    true_only_strings: bool = False,
    empty_is_default: bool = True,
) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value

    text = _normalized_text(value)
    if not text and empty_is_default:
        return bool(default)

    false_lookup = _normalized_tokens(false_values)
    if text in false_lookup:
        return False
    true_lookup = _normalized_tokens(true_values)
    if true_only_strings:
        return text in true_lookup if isinstance(value, str) else bool(value)
    if false_only_strings:
        return True if isinstance(value, str) else bool(value)

    if text in true_lookup:
        return True
    return bool(default)


def env_bool(
    name: str,
    *,
    true_values: Iterable[str] = ENV_TRUE_VALUES,
    false_values: Iterable[str] = ENV_FALSE_VALUES,
) -> bool | None:
    value = os.environ.get(name)
    if value is None:
        return None
    text = _normalized_text(value)
    if text in _normalized_tokens(false_values):
        return False
    if text in _normalized_tokens(true_values):
        return True
    return None


__all__ = [
    "DEFAULT_FALSE_VALUES",
    "DEFAULT_TRUE_VALUES",
    "ENV_FALSE_VALUES",
    "ENV_TRUE_VALUES",
    "KOREAN_FALSE_VALUES",
    "env_bool",
    "positive_int",
    "setting_bool",
]
