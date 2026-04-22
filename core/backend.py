# Version: 02.02.00
# Phase: PHASE1-B
"""
core/backend.py
하위 호환 shim — 기존 `from core.backend import CoreBackend` 유지
실제 구현은 core/pipeline/ 패키지로 이전됨
"""
from core.pipeline.backend_core import CoreBackend  # noqa: F401

__all__ = ["CoreBackend"]
