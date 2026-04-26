# Version: 02.03.00
# Phase: PHASE1-B

# Phase: PHASE1-B
"""
core/pipeline/__init__.py
Pipeline 패키지 — CoreBackend 재수출
"""
from core.pipeline.backend_core import CoreBackend   # noqa: F401

__all__ = ["CoreBackend"]
