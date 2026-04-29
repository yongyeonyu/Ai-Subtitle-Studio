# Version: 03.00.00
# Phase: PHASE2
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class FrameSample:
    timestamp: float
    data: bytes | Sequence[int]


@dataclass(frozen=True, slots=True)
class SceneChange:
    start: float
    end: float
    score: float
    is_cut: bool


def mean_abs_rgb_difference(frame_a: bytes | Sequence[int], frame_b: bytes | Sequence[int]) -> float:
    """Estimate scene change with a tiny dependency-free pixel delta."""
    length = min(len(frame_a), len(frame_b))
    if length <= 0:
        return 0.0

    total = 0
    for index in range(length):
        total += abs(int(frame_a[index]) - int(frame_b[index]))
    return total / length


def classify_scene_change(score: float, threshold: float = 18.0) -> bool:
    return float(score) >= max(0.0, float(threshold))


def detect_scene_changes(samples: Iterable[FrameSample], threshold: float = 18.0) -> list[SceneChange]:
    ordered = sorted(samples, key=lambda sample: sample.timestamp)
    changes: list[SceneChange] = []
    for previous, current in zip(ordered, ordered[1:]):
        score = mean_abs_rgb_difference(previous.data, current.data)
        is_cut = classify_scene_change(score, threshold=threshold)
        if is_cut:
            changes.append(SceneChange(previous.timestamp, current.timestamp, score, is_cut))
    return changes
