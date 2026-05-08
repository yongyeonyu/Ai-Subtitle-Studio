from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.optimization.backend_policy import normalize_backend_policy, profile_backend
from core.video_preview_proxy import cut_boundary_scan_source


@dataclass(frozen=True, slots=True)
class CutBoundaryBackendChoice:
    backend: str
    scan_path: str
    reason: str
    use_proxy: bool


def select_cut_boundary_backend(path: str, settings: dict[str, Any] | None = None) -> CutBoundaryBackendChoice:
    data = dict(settings or {})
    original = str(path or "")
    policy = normalize_backend_policy(data.get("cut_boundary_backend_policy", "auto"))
    prof = profile_backend("cut_boundary", data) or profile_backend("cut", data)
    if policy == "legacy":
        return CutBoundaryBackendChoice("legacy_opencv", original, "legacy_policy", False)
    if prof and policy == "auto":
        scan_path = cut_boundary_scan_source(original, data)
        return CutBoundaryBackendChoice(prof, scan_path, "autotuned_profile", bool(scan_path != original))
    if policy == "native":
        scan_path = cut_boundary_scan_source(original, data)
        return CutBoundaryBackendChoice("native_opencv", scan_path, "native_policy", bool(scan_path != original))
    if policy == "fast":
        scan_path = cut_boundary_scan_source(original, data)
        return CutBoundaryBackendChoice("opencv_proxy_fast", scan_path, "fast_policy", bool(scan_path != original))
    scan_path = cut_boundary_scan_source(original, data)
    return CutBoundaryBackendChoice("opencv_strict", scan_path, "auto_strict", bool(scan_path != original))


def apply_cut_boundary_backend_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(settings or {})
    policy = normalize_backend_policy(data.get("cut_boundary_backend_policy", "auto"))
    prof = profile_backend("cut_boundary", data) or profile_backend("cut", data)
    backend = prof if policy == "auto" and prof else policy
    if backend in {"fast", "native", "opencv_proxy_fast", "native_opencv"}:
        data.setdefault("scan_cut_cv2_threads_per_worker", 1)
        data.setdefault("scan_cut_pioneer_sequential_decode_enabled", True)
        data.setdefault("scan_cut_ffmpeg_scene_prepass_enabled", True)
        data.setdefault("scan_cut_ffmpeg_scene_replace_opencv_enabled", True)
        data.setdefault("scan_cut_ffmpeg_scene_threshold", 0.30)
        data.setdefault("scan_cut_ffmpeg_scene_timeout_sec", 90.0)
        data.setdefault("scan_cut_ffmpeg_scene_max_candidates", 300)
        data.setdefault("scan_cut_progress_sample_stride", 8)
        if "scan_cut_pioneer_workers" not in data:
            data["scan_cut_pioneer_workers"] = 4
        if "scan_cut_verify_workers" not in data:
            data["scan_cut_verify_workers"] = 4
    return data


__all__ = [
    "CutBoundaryBackendChoice",
    "apply_cut_boundary_backend_settings",
    "select_cut_boundary_backend",
]
