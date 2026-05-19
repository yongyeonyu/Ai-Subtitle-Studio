from __future__ import annotations

from typing import Any


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"0", "false", "off", "no", "n", "끔", "아니오"}:
            return False
        if text in {"1", "true", "on", "yes", "y", "켬", "예"}:
            return True
    return bool(value)


def audio_filter_display_name(settings: dict[str, Any] | None) -> str:
    data = dict(settings or {})
    selected = str(data.get("selected_audio_ai", "none") or "none").strip().lower()
    auto_selected = _truthy(data.get("_runtime_auto_audio_ai_selected"), False)

    if selected == "none":
        label = "FFMPEG 기본필터" if _truthy(data.get("use_basic_filter"), True) else "미사용"
    else:
        label = {
            "deepfilter": "DeepFilter",
            "rnnoise": "RNNoise",
            "resemble_enhance": "Resemble",
            "clearvoice": "ClearVoice",
        }.get(selected, str(data.get("selected_audio_ai") or "미사용"))

    if auto_selected:
        return f"{label} 자동"
    return label


__all__ = ["audio_filter_display_name"]
