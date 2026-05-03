"""
Sidebar preset panel helpers extracted from ui.home_ui.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QMessageBox

from core.audio import audio_presets as _audio_presets
from core.audio.preset_auto_classifier import (
    apply_auto_classified_presets,
    auto_classify_media_presets,
)
from core.audio.stt_quality_presets import (
    apply_stt_quality_preset,
    normalize_stt_quality_key,
)
from core.settings import load_settings


def _resolve_audio_preset_combo_data(settings: dict | None) -> str:
    resolver = getattr(_audio_presets, "resolve_audio_preset_combo_data", None)
    if callable(resolver):
        return str(resolver(settings))

    data = dict(settings or {})
    preset_name = str(data.get("audio_preset", "") or "").strip()
    if preset_name:
        return preset_name

    default_apply_data = dict(getattr(_audio_presets, "DEFAULT_AUDIO_APPLY_DATA", {}) or {})
    if default_apply_data and all(data.get(key) == value for key, value in default_apply_data.items()):
        return "__default__"
    return ""


def sync_sidebar_preset_panel(host, settings: dict | None = None) -> None:
    settings = dict(settings or load_settings())
    host._set_combo_data_silent(
        getattr(host, "sidebar_stt_quality_combo", None),
        normalize_stt_quality_key(settings.get("stt_quality_preset", "balanced")),
    )
    host._set_combo_data_silent(
        getattr(host, "sidebar_audio_preset_combo", None),
        _resolve_audio_preset_combo_data(settings),
    )

    auto_btn = getattr(host, "sidebar_auto_preset_btn", None)
    if auto_btn is not None:
        try:
            decision = dict(settings.get("audio_preset_auto_decision") or {})
            highlighted = bool(decision.get("audio_preset") and decision.get("stt_quality_preset"))
            icon_color = "#34C759" if highlighted else "#A9B0B7"
            auto_btn.setIcon(host._nav_icon("auto", icon_color))
            auto_btn.setToolTip(
                str(decision.get("reason") or "영상 기준 자동 판정")
                if highlighted
                else "영상 기준 자동 판정"
            )
        except RuntimeError:
            pass

    combo = getattr(host, "sidebar_cut_boundary_combo", None)
    if combo is None:
        return

    try:
        from core.cut_boundary import cut_boundary_level

        current_level = cut_boundary_level(settings)
    except Exception:
        enabled = bool(settings.get("cut_boundary_detection_enabled", settings.get("scan_cut_enabled", True)))
        current_level = "medium" if enabled else "off"

    try:
        combo.blockSignals(True)
        existing_data = [combo.itemData(i) for i in range(combo.count())]
        if not all(x in existing_data for x in ("off", "low", "medium")) or any(x == "high" for x in existing_data):
            combo.clear()
            combo.addItem("사용안함", "off")
            combo.addItem("낮음", "low")
            combo.addItem("중간", "medium")

        for i in range(combo.count()):
            if combo.itemData(i) == current_level:
                combo.setCurrentIndex(i)
                break
        else:
            combo.setCurrentIndex(2 if combo.count() >= 3 else 0)
    except RuntimeError:
        host.sidebar_cut_boundary_combo = None
    finally:
        try:
            combo.blockSignals(False)
        except RuntimeError:
            pass


def apply_sidebar_settings_update(host, updates: dict | None = None, preset_applier=None) -> dict:
    settings = dict(load_settings())
    if callable(preset_applier):
        settings = dict(preset_applier(settings))
    if updates:
        settings.update(updates)
    host._apply_ai_settings(settings)
    sync_sidebar_preset_panel(host, settings)
    return settings


def on_sidebar_stt_quality_changed(host) -> None:
    combo = getattr(host, "sidebar_stt_quality_combo", None)
    if combo is None:
        return
    apply_sidebar_settings_update(
        host,
        preset_applier=lambda settings: apply_stt_quality_preset(settings, combo.currentData() or "balanced"),
    )


def on_sidebar_audio_preset_changed(host) -> None:
    combo = getattr(host, "sidebar_audio_preset_combo", None)
    if combo is None:
        return
    preset_name = combo.currentData() or ""
    if preset_name == "__default__":
        default_applier = getattr(_audio_presets, "apply_default_audio_preset", None)
        if callable(default_applier):
            apply_sidebar_settings_update(host, preset_applier=default_applier)
        else:
            apply_sidebar_settings_update(host, {"audio_preset": ""})
        return
    if preset_name:
        apply_sidebar_settings_update(
            host,
            preset_applier=lambda settings: _audio_presets.apply_audio_preset(settings, preset_name),
        )
        return
    apply_sidebar_settings_update(host, {"audio_preset": ""})


def on_sidebar_auto_preset_detect(host) -> None:
    media_path = host._current_editor_media_path()
    if not media_path:
        QMessageBox.information(host, "자동 판정", "현재 에디터에 열린 영상이 없어서 자동 판정을 진행할 수 없습니다.")
        return
    settings = dict(load_settings())
    try:
        decision = auto_classify_media_presets(media_path, settings=settings)
        updated = apply_auto_classified_presets(settings, decision)
        host._apply_ai_settings(updated)
        sync_sidebar_preset_panel(host, updated)
        QMessageBox.information(
            host,
            "자동 판정 완료",
            (
                f"오디오: {decision['audio_preset']}\n"
                f"정밀인식: {decision['stt_quality_preset']}\n"
                f"신뢰도: {int(round(float(decision.get('confidence', 0.0)) * 100))}%\n\n"
                f"{decision.get('reason', '')}"
            ),
        )
    except Exception as exc:
        QMessageBox.warning(host, "자동 판정 실패", str(exc))
