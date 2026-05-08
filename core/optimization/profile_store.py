from __future__ import annotations

import os
from time import time
from typing import Any

from core.json_file import read_json_file, write_json_file_atomic
from core.runtime import config

from .types import OptimizationProfile


def optimization_profile_path(dataset_dir: str | None = None) -> str:
    return os.path.join(dataset_dir or config.DATASET_DIR, "runtime_optimization_profile.json")


def load_optimization_profile(dataset_dir: str | None = None) -> OptimizationProfile:
    payload = read_json_file(
        optimization_profile_path(dataset_dir),
        default={},
        expected_type=dict,
        context="runtime_optimization_profile",
        log_errors=False,
    )
    return OptimizationProfile.from_dict(payload)


def save_optimization_profile(
    profile: OptimizationProfile | dict[str, Any],
    *,
    dataset_dir: str | None = None,
) -> None:
    if isinstance(profile, OptimizationProfile):
        data = profile.to_dict()
    else:
        data = OptimizationProfile.from_dict(dict(profile or {})).to_dict()
    data["updated_at"] = float(time())
    write_json_file_atomic(optimization_profile_path(dataset_dir), data)
