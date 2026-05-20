from __future__ import annotations

import os
from typing import Any

from core.runtime.logger import get_logger
from core.settings import load_settings


def _log_memory_guard_nonfatal(step: str, exc: BaseException) -> None:
    try:
        get_logger().log(f"  ⚠️ [자막 메모리] {step} 실패: {type(exc).__name__}: {exc}")
    except (OSError, RuntimeError, ValueError):
        pass


def create_subtitle_generation_memory_guard(owner: Any, target_file, queue_index: int):
    """Create the per-generation memory guard without bloating the pipeline loop."""
    try:
        settings = load_settings()
        if not bool(settings.get("subtitle_generation_memory_guard_enabled", True)):
            return None
        from core.runtime.memory_manager import SubtitleGenerationMemoryGuard

        def _pressure_callback(stage, snapshot, qi=queue_index):
            subtitle_stage = str(snapshot.get("subtitle_generation_stage", "") or "")
            if stage not in {"warning", "critical"}:
                return
            status = "🧹 [자막 메모리] "
            status += "강제 정리" if stage == "critical" else "정리"
            if subtitle_stage:
                status += f" · {subtitle_stage}"
            try:
                owner._emit_processing_stage(qi, status)
            except Exception as exc:
                _log_memory_guard_nonfatal("stage status emit", exc)

        guard = SubtitleGenerationMemoryGuard(
            settings=settings,
            logger=get_logger(),
            pressure_callback=_pressure_callback,
        )
        guard.checkpoint(
            f"generation_start:{os.path.basename(str(target_file))}",
            force=True,
        )
        return guard
    except Exception as exc:
        _log_memory_guard_nonfatal("단계별 감시 준비", exc)
        return None


def subtitle_generation_memory_checkpoint(
    guard,
    stage: str,
    *,
    include_gpu: bool = False,
    cleanup: bool = False,
    force: bool = False,
) -> dict:
    if guard is None:
        return {}
    try:
        return guard.checkpoint(
            stage,
            include_gpu=include_gpu,
            cleanup=cleanup,
            force=force,
        )
    except Exception as exc:
        _log_memory_guard_nonfatal(f"checkpoint {stage}", exc)
        return {}


__all__ = [
    "create_subtitle_generation_memory_guard",
    "subtitle_generation_memory_checkpoint",
]
