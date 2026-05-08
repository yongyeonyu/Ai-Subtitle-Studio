from __future__ import annotations

from dataclasses import asdict, dataclass, field
from time import time
from typing import Any


@dataclass(frozen=True, slots=True)
class BackendCandidate:
    task: str
    name: str
    available: bool
    reason: str = ""
    platform: str = "any"
    priority: int = 0
    quality_tier: str = "balanced"
    model: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    task: str
    backend: str
    elapsed_sec: float
    model: str = ""
    quality: dict[str, float] = field(default_factory=dict)
    resources: dict[str, float] = field(default_factory=dict)
    passed_quality_gate: bool = False
    created_at: float = field(default_factory=time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class OptimizationProfile:
    schema: str = "ai_subtitle_studio.runtime_optimization_profile.v1"
    selected_backends: dict[str, str] = field(default_factory=dict)
    selected_models: dict[str, str] = field(default_factory=dict)
    benchmarks: list[dict[str, Any]] = field(default_factory=list)
    quality_gates: dict[str, dict[str, float]] = field(default_factory=dict)
    updated_at: float = field(default_factory=time)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "OptimizationProfile":
        data = dict(payload or {})
        return cls(
            schema=str(data.get("schema") or cls.schema),
            selected_backends={
                str(k): str(v)
                for k, v in dict(data.get("selected_backends") or {}).items()
                if str(k).strip() and str(v).strip()
            },
            selected_models={
                str(k): str(v)
                for k, v in dict(data.get("selected_models") or {}).items()
                if str(k).strip() and str(v).strip()
            },
            benchmarks=[
                dict(row)
                for row in list(data.get("benchmarks") or [])
                if isinstance(row, dict)
            ],
            quality_gates={
                str(k): {
                    str(inner_key): float(inner_value)
                    for inner_key, inner_value in dict(v or {}).items()
                    if _is_number(inner_value)
                }
                for k, v in dict(data.get("quality_gates") or {}).items()
            },
            updated_at=float(data.get("updated_at") or time()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "selected_backends": dict(self.selected_backends),
            "selected_models": dict(self.selected_models),
            "benchmarks": list(self.benchmarks),
            "quality_gates": {
                str(key): dict(value)
                for key, value in dict(self.quality_gates).items()
            },
            "updated_at": float(self.updated_at or time()),
        }


def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except Exception:
        return False
