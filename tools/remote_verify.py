#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.automation.app_command_protocol import build_command_payload
from tools.automation_command_client import send_app_command_with_readiness_retry

_LIVE_NLE_TRACK_ORDER = ("VAD", "STT1", "STT2", "subtitle_preview", "final")
_LIVE_NLE_REQUIRED_RUNTIME_TRACKS = ("VAD", "STT1", "STT2")
_LIVE_NLE_DEFAULT_MIN_PRE_FINAL_OBSERVATIONS = 2
_EDITOR_SEQUENCE_POST_STEP_STATUS_TIMEOUT_SEC = 4.0
_EDITOR_SEQUENCE_SNAPSHOT_TIMEOUT_SEC = 8.0
_EDITOR_SEQUENCE_ARTIFACT_COMMANDS = {
    "capture-active-dialog",
    "capture-dictionary-snapshot",
    "export-subtitles",
    "export-subtitle-video",
}


def _default_output_dir(label: str) -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return ROOT / "output" / "manual_verification" / f"{label}_{stamp}"


def _safe_slug(text: str) -> str:
    raw = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in str(text or "").strip().lower())
    return raw.strip("-") or "step"


def _send(command: str, *, timeout: float, path: str = "", options: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = build_command_payload(command, path=path, options=dict(options or {}))
    return send_app_command_with_readiness_retry(payload, timeout_sec=float(timeout))


def _wait_for_snapshot(path: str, *, timeout_sec: float = 6.0) -> bool:
    target = str(path or "").strip()
    if not target:
        return False
    deadline = time.monotonic() + max(0.2, float(timeout_sec or 6.0))
    while time.monotonic() < deadline:
        if os.path.isfile(target) and os.path.getsize(target) > 0:
            return True
        time.sleep(0.1)
    return os.path.isfile(target)


def _file_state(path: str) -> dict[str, Any]:
    target = str(path or "").strip()
    exists = bool(target) and os.path.isfile(target)
    size = int(os.path.getsize(target)) if exists else 0
    return {"path": target, "path_exists": exists, "path_size": size}


def _capture_status(timeout: float) -> dict[str, Any]:
    try:
        return _send("status", timeout=timeout)
    except OSError as exc:
        return {"ok": False, "error": "app_unreachable", "message": str(exc), "data": {}}


def _bounded_probe_timeout(timeout: float, *, cap: float) -> float:
    return max(1.0, min(float(timeout or 1.0), float(cap)))


def _result_artifact_paths(command: str, result: dict[str, Any] | None) -> list[str]:
    if command != "export-subtitle-video" or not isinstance(result, dict):
        return []
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    paths: list[str] = []
    for row in list(data.get("outputs") or []):
        if not isinstance(row, dict):
            continue
        mov_output = row.get("mov_output") if isinstance(row.get("mov_output"), dict) else {}
        path = str(mov_output.get("path", "") or "").strip()
        if path:
            paths.append(path)
    return paths


def _result_data(result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    data = result.get("data")
    return dict(data or {}) if isinstance(data, dict) else {}


def _live_nle_track_counts(data: dict[str, Any]) -> dict[str, int]:
    raw_counts = data.get("nle_runtime_track_counts")
    if not isinstance(raw_counts, dict):
        tracks = data.get("nle_runtime_tracks")
        if isinstance(tracks, dict) and isinstance(tracks.get("counts"), dict):
            raw_counts = tracks.get("counts")
        elif isinstance(data.get("editor_runtime"), dict):
            editor_tracks = data["editor_runtime"].get("nle_runtime_tracks")
            if isinstance(editor_tracks, dict) and isinstance(editor_tracks.get("counts"), dict):
                raw_counts = editor_tracks.get("counts")
    counts: dict[str, int] = {}
    for track in _LIVE_NLE_TRACK_ORDER:
        try:
            counts[track] = max(0, int((raw_counts or {}).get(track, 0) or 0))
        except Exception:
            counts[track] = 0
    return counts


def _contains_raw_runtime_payload(value: Any) -> bool:
    if isinstance(value, dict):
        for key, raw in value.items():
            normalized = str(key or "").strip().lower()
            if normalized in {
                "segments",
                "runtime_track_segments",
                "stt_preview_segments",
                "subtitle_preview_segments",
                "vad_segments",
                "voice_activity_segments",
            }:
                return True
            if normalized == "text":
                return True
            if _contains_raw_runtime_payload(raw):
                return True
    elif isinstance(value, list):
        return any(_contains_raw_runtime_payload(item) for item in value)
    return False


def _compact_runtime_track_contract(data: dict[str, Any]) -> dict[str, Any]:
    tracks = data.get("nle_runtime_tracks")
    if not isinstance(tracks, dict) and isinstance(data.get("editor_runtime"), dict):
        tracks = data["editor_runtime"].get("nle_runtime_tracks")
    tracks = dict(tracks or {}) if isinstance(tracks, dict) else {}
    source_tracks = tracks.get("tracks") if isinstance(tracks.get("tracks"), dict) else {}
    authority: dict[str, bool] = {}
    role: dict[str, str] = {}
    for track in _LIVE_NLE_TRACK_ORDER:
        raw = source_tracks.get(track) if isinstance(source_tracks, dict) else {}
        raw_track = dict(raw or {}) if isinstance(raw, dict) else {}
        authority[track] = bool(raw_track.get("authoritative_for_save_export", track == "final"))
        role[track] = str(raw_track.get("role") or ("save_export_render_authority" if track == "final" else "runtime_reference_only"))
    return {
        "compact_payload": bool(tracks.get("compact_payload", True)),
        "raw_payload_leak": _contains_raw_runtime_payload(tracks),
        "authority": authority,
        "role": role,
        "final_authority_ok": authority.get("final") is True
        and all(authority.get(track) is False for track in _LIVE_NLE_TRACK_ORDER if track != "final"),
    }


def _live_nle_budget_contract(data: dict[str, Any]) -> dict[str, Any]:
    runtime_resource = data.get("runtime_resource") if isinstance(data.get("runtime_resource"), dict) else {}
    budget = (
        runtime_resource.get("live_nle_projection_budget")
        if isinstance(runtime_resource.get("live_nle_projection_budget"), dict)
        else {}
    )
    budget = dict(budget or {})
    if not budget:
        return {"present": False, "ok": False, "fields": {}}
    fields = {
        "dedicated_worker_count": budget.get("dedicated_worker_count"),
        "max_projection_workers": budget.get("max_projection_workers"),
        "shares_subtitle_worker_pool": budget.get("shares_subtitle_worker_pool"),
        "uses_existing_row_snapshots": budget.get("uses_existing_row_snapshots"),
        "coalesces_updates": budget.get("coalesces_updates"),
        "drops_stale_preview_frames": budget.get("drops_stale_preview_frames"),
        "quality_policy": budget.get("quality_policy"),
    }
    ok = (
        fields["dedicated_worker_count"] == 0
        and fields["max_projection_workers"] == 0
        and fields["shares_subtitle_worker_pool"] is False
        and fields["uses_existing_row_snapshots"] is True
        and fields["coalesces_updates"] is True
        and fields["drops_stale_preview_frames"] is True
        and fields["quality_policy"] == "final_authority_unchanged"
    )
    return {"present": True, "ok": ok, "fields": fields}


def _live_nle_generation_completed(data: dict[str, Any]) -> bool:
    guided = data.get("guided_snapshot_run") if isinstance(data.get("guided_snapshot_run"), dict) else {}
    stage_key = str(data.get("last_stage_key") or guided.get("last_stage_key") or "").strip().lower()
    stage = str(data.get("generation_stage") or guided.get("last_stage") or guided.get("last_stage_label") or "").strip()
    if stage_key == "completed" or "완료" in stage or "completed" in stage.lower():
        return True
    if bool(data.get("status_handler_timeout")) or bool(data.get("status_response_cached")):
        return False
    explicit_activity_fields = all(key in data for key in ("editor_state", "backend_active", "auto_processing_active"))
    return (
        explicit_activity_fields
        and bool(guided)
        and not bool(guided.get("active", False))
        and not bool(data.get("backend_active", False))
        and not bool(data.get("auto_processing_active", False))
        and str(data.get("editor_state") or "") != "ST_PROC"
    )


def _live_nle_sample_from_status(
    result: dict[str, Any],
    *,
    elapsed_sec: float,
    latency_sec: float,
    command: str = "guided-subtitle-status",
    poll_index: int | None = None,
) -> dict[str, Any]:
    data = _result_data(result)
    guided = data.get("guided_snapshot_run") if isinstance(data.get("guided_snapshot_run"), dict) else {}
    counts = _live_nle_track_counts(data)
    compact_contract = _compact_runtime_track_contract(data)
    budget_contract = _live_nle_budget_contract(data)
    active = (
        bool(guided.get("active", False))
        or bool(data.get("backend_active", False))
        or bool(data.get("auto_processing_active", False))
        or str(data.get("editor_state") or "") == "ST_PROC"
    )
    completed = _live_nle_generation_completed(data)
    try:
        subtitle_count = int(data.get("subtitle_count") or 0)
    except Exception:
        subtitle_count = 0
    return {
        "command": str(command or ""),
        "poll_index": int(poll_index) if poll_index is not None else None,
        "elapsed_sec": round(float(elapsed_sec or 0.0), 3),
        "latency_sec": round(float(latency_sec or 0.0), 3),
        "ok": bool(result.get("ok", False)) if isinstance(result, dict) else False,
        "error": str(result.get("error", "") or "") if isinstance(result, dict) else "",
        "status_handler_timeout": bool(data.get("status_handler_timeout", False)),
        "status_response_cached": bool(data.get("status_response_cached", False)),
        "status_snapshot_fallback": bool(data.get("status_snapshot_fallback", False)),
        "status_response_truncated": bool(data.get("status_response_truncated", False)),
        "status_response_original_bytes": int(data.get("status_response_original_bytes", 0) or 0),
        "editor_state": str(data.get("editor_state") or ""),
        "backend_active": bool(data.get("backend_active", False)),
        "auto_processing_active": bool(data.get("auto_processing_active", False)),
        "guided_active": bool(guided.get("active", False)),
        "last_stage_key": str(data.get("last_stage_key") or guided.get("last_stage_key") or ""),
        "generation_stage": str(data.get("generation_stage") or guided.get("last_stage") or guided.get("last_stage_label") or ""),
        "subtitle_count": subtitle_count,
        "nle_runtime_track_counts": counts,
        "pre_final_active": bool(active and not completed),
        "generation_completed": bool(completed),
        "compact_runtime_track_contract": compact_contract,
        "live_nle_projection_budget_contract": budget_contract,
    }


def _pre_final_observation_summary(
    samples: list[dict[str, Any]],
    *,
    min_observations: int,
) -> tuple[dict[str, dict[str, Any]], dict[str, int], list[str], list[str]]:
    required_min = max(1, int(min_observations or 1))
    observed: dict[str, dict[str, Any]] = {}
    observation_counts: dict[str, int] = {}
    missing: list[str] = []
    insufficient: list[str] = []
    for track in _LIVE_NLE_REQUIRED_RUNTIME_TRACKS:
        track_samples: list[dict[str, Any]] = []
        seen_keys: set[Any] = set()
        for index, sample in enumerate(samples):
            counts = sample.get("nle_runtime_track_counts") if isinstance(sample.get("nle_runtime_track_counts"), dict) else {}
            if not bool(sample.get("pre_final_active")) or int(counts.get(track, 0) or 0) <= 0:
                continue
            key = sample.get("poll_index")
            if key is None:
                key = index
            if key in seen_keys:
                continue
            seen_keys.add(key)
            track_samples.append(sample)
        observation_counts[track] = len(track_samples)
        if not track_samples:
            missing.append(track)
            continue
        if len(track_samples) < required_min:
            insufficient.append(track)
            continue
        first = track_samples[0]
        last = track_samples[-1]
        max_count = max(
            int((sample.get("nle_runtime_track_counts") or {}).get(track, 0) or 0)
            for sample in track_samples
        )
        observed[track] = {
            "first_elapsed_sec": first.get("elapsed_sec"),
            "last_elapsed_sec": last.get("elapsed_sec"),
            "observation_count": len(track_samples),
            "max_count": max_count,
            "stage": last.get("generation_stage"),
        }
    return observed, observation_counts, missing, insufficient


def _build_live_nle_runtime_proof_report(
    *,
    media_path: str,
    output_dir: Path,
    start_result: dict[str, Any],
    samples: list[dict[str, Any]],
    snapshot_dir: Path,
    started_at: str,
    ended_at: str,
    min_pre_final_observations: int = _LIVE_NLE_DEFAULT_MIN_PRE_FINAL_OBSERVATIONS,
) -> dict[str, Any]:
    required_min = max(1, int(min_pre_final_observations or 1))
    observed, observation_counts, missing, insufficient = _pre_final_observation_summary(
        samples,
        min_observations=required_min,
    )
    failed_samples = [sample for sample in samples if not bool(sample.get("ok", False))]
    raw_payload_leaks = [
        sample.get("elapsed_sec")
        for sample in samples
        if bool((sample.get("compact_runtime_track_contract") or {}).get("raw_payload_leak", False))
    ]
    compact_payload_failures = [
        sample.get("elapsed_sec")
        for sample in samples
        if not bool((sample.get("compact_runtime_track_contract") or {}).get("compact_payload", True))
    ]
    final_authority_failures = [
        sample.get("elapsed_sec")
        for sample in samples
        if not bool((sample.get("compact_runtime_track_contract") or {}).get("final_authority_ok", True))
    ]
    budget_failures = [
        sample.get("elapsed_sec")
        for sample in samples
        if bool(sample.get("pre_final_active"))
        and not bool((sample.get("live_nle_projection_budget_contract") or {}).get("ok", False))
    ]
    status_handler_timeout_elapsed = [
        sample.get("elapsed_sec") for sample in samples if bool(sample.get("status_handler_timeout", False))
    ]
    status_response_cached_elapsed = [
        sample.get("elapsed_sec") for sample in samples if bool(sample.get("status_response_cached", False))
    ]
    status_snapshot_fallback_elapsed = [
        sample.get("elapsed_sec") for sample in samples if bool(sample.get("status_snapshot_fallback", False))
    ]
    status_response_truncated_elapsed = [
        sample.get("elapsed_sec") for sample in samples if bool(sample.get("status_response_truncated", False))
    ]
    snapshot_files = sorted(str(path.relative_to(output_dir)) for path in snapshot_dir.glob("*.png")) if snapshot_dir.is_dir() else []
    issues: list[str] = []
    if not bool(start_result.get("ok", False)):
        issues.append("guided_subtitle_run_start_failed")
    if missing:
        issues.append("missing_pre_final_tracks:" + ",".join(missing))
    if insufficient:
        issues.append("insufficient_pre_final_observations:" + ",".join(insufficient))
    if failed_samples:
        issues.append("status_poll_failed")
    if raw_payload_leaks:
        issues.append("raw_runtime_payload_leak")
    if compact_payload_failures:
        issues.append("compact_runtime_payload_contract_failed")
    if final_authority_failures:
        issues.append("final_authority_contract_failed")
    if budget_failures:
        issues.append("live_projection_budget_contract_failed")
    generation_completed = any(bool(sample.get("generation_completed")) for sample in samples)
    if not generation_completed:
        issues.append("generation_not_completed")
    status = "passed" if not issues else "blocked"
    return {
        "schema": "ai_subtitle_studio.live_nle_runtime_proof.v2",
        "status": status,
        "media_path": str(media_path or ""),
        "output_dir": str(output_dir),
        "snapshot_dir": str(snapshot_dir),
        "started_at": started_at,
        "ended_at": ended_at,
        "start_result_ok": bool(start_result.get("ok", False)),
        "sample_count": len(samples),
        "failed_sample_count": len(failed_samples),
        "generation_completed": generation_completed,
        "required_tracks": list(_LIVE_NLE_REQUIRED_RUNTIME_TRACKS),
        "min_pre_final_observations": required_min,
        "observed_pre_final_tracks": observed,
        "pre_final_observation_counts": observation_counts,
        "missing_pre_final_tracks": missing,
        "insufficient_pre_final_observation_tracks": insufficient,
        "raw_payload_leak_elapsed_sec": raw_payload_leaks,
        "compact_payload_failure_elapsed_sec": compact_payload_failures,
        "final_authority_failure_elapsed_sec": final_authority_failures,
        "budget_failure_elapsed_sec": budget_failures,
        "status_handler_timeout_elapsed_sec": status_handler_timeout_elapsed,
        "status_response_cached_elapsed_sec": status_response_cached_elapsed,
        "status_snapshot_fallback_elapsed_sec": status_snapshot_fallback_elapsed,
        "status_response_truncated_elapsed_sec": status_response_truncated_elapsed,
        "snapshot_files": snapshot_files,
        "issues": issues,
        "samples": samples,
        "notes": [
            "This proof records runtime/status observability only.",
            "It does not by itself approve subtitle quality, conversion-speed regression, App Store packaging, or persisted NLE disk-format cutover.",
        ],
    }


def _write_live_nle_runtime_proof(output_dir: Path, report: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "live_nle_runtime_proof.json").write_text(
        json.dumps({key: value for key, value in report.items() if key != "samples"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "status_samples.json").write_text(
        json.dumps(report.get("samples", []), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    jsonl_lines = [json.dumps(sample, ensure_ascii=False, sort_keys=True) for sample in list(report.get("samples") or [])]
    (output_dir / "observability_samples.jsonl").write_text(
        ("\n".join(jsonl_lines) + "\n") if jsonl_lines else "",
        encoding="utf-8",
    )
    lines = [
        "# Live NLE Runtime Proof",
        "",
        f"- status: `{report.get('status')}`",
        f"- media_path: `{report.get('media_path')}`",
        f"- sample_count: `{report.get('sample_count')}`",
        f"- min_pre_final_observations: `{report.get('min_pre_final_observations')}`",
        f"- generation_completed: `{report.get('generation_completed')}`",
        f"- issues: `{', '.join(report.get('issues') or []) or 'none'}`",
        "",
        "## Required Runtime Tracks",
        "",
        "| Track | Observed before final | Observations | First elapsed | Last elapsed | Max count | Stage |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    observed = report.get("observed_pre_final_tracks") if isinstance(report.get("observed_pre_final_tracks"), dict) else {}
    observation_counts = (
        report.get("pre_final_observation_counts") if isinstance(report.get("pre_final_observation_counts"), dict) else {}
    )
    for track in report.get("required_tracks") or []:
        item = observed.get(track) if isinstance(observed, dict) else None
        lines.append(
            "| {track} | {ok} | {observations} | {first_elapsed} | {last_elapsed} | {max_count} | {stage} |".format(
                track=track,
                ok="yes" if isinstance(item, dict) else "no",
                observations=(item or {}).get("observation_count", observation_counts.get(track, 0)),
                first_elapsed=(item or {}).get("first_elapsed_sec", ""),
                last_elapsed=(item or {}).get("last_elapsed_sec", ""),
                max_count=(item or {}).get("max_count", ""),
                stage=(item or {}).get("stage", ""),
            )
        )
    lines.extend(
        [
            "",
            "## Guard Summary",
            "",
            f"- Raw runtime payload leak elapsed samples: `{report.get('raw_payload_leak_elapsed_sec')}`",
            f"- Compact payload failure elapsed samples: `{report.get('compact_payload_failure_elapsed_sec')}`",
            f"- Final-authority failure elapsed samples: `{report.get('final_authority_failure_elapsed_sec')}`",
            f"- Live projection budget failure elapsed samples: `{report.get('budget_failure_elapsed_sec')}`",
            f"- Status handler timeout elapsed samples: `{report.get('status_handler_timeout_elapsed_sec')}`",
            f"- Cached status elapsed samples: `{report.get('status_response_cached_elapsed_sec')}`",
            f"- Status fallback elapsed samples: `{report.get('status_snapshot_fallback_elapsed_sec')}`",
            f"- Truncated status elapsed samples: `{report.get('status_response_truncated_elapsed_sec')}`",
            f"- Snapshot files: `{report.get('snapshot_files')}`",
            f"- JSONL samples: `observability_samples.jsonl`",
            "",
            "## Notes",
            "",
        ]
    )
    for note in list(report.get("notes") or []):
        lines.append(f"- {note}")
    (output_dir / "live_nle_runtime_proof.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_live_nle_proof(args: argparse.Namespace) -> int:
    label = args.label or "live_nle_runtime_proof"
    output_dir = Path(args.output_dir).resolve() if args.output_dir else _default_output_dir(label)
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_dir = output_dir / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    media_path = str(Path(args.media).resolve()) if str(args.media or "").strip() else ""
    poll_sec = max(0.1, float(args.poll_sec or 1.0))
    max_duration_sec = max(poll_sec, float(args.max_duration_sec or 120.0))
    status_timeout = max(0.5, float(args.timeout or 8.0))
    min_pre_final_observations = max(1, int(args.min_pre_final_observations or _LIVE_NLE_DEFAULT_MIN_PRE_FINAL_OBSERVATIONS))

    start_result: dict[str, Any] = {"ok": False, "error": "media_missing", "data": {}}
    if media_path and os.path.isfile(media_path):
        try:
            start_result = _send(
                "guided-subtitle-run",
                timeout=max(status_timeout, float(args.start_timeout or status_timeout)),
                path=media_path,
                options={"snapshot_dir": str(snapshot_dir)},
            )
        except OSError as exc:
            start_result = {"ok": False, "error": "app_unreachable", "message": str(exc), "data": {}}

    samples: list[dict[str, Any]] = []
    start_error = str(start_result.get("error") or "")
    if start_error in {"media_missing", "app_unreachable"}:
        ended_at = time.strftime("%Y-%m-%d %H:%M:%S")
        report = _build_live_nle_runtime_proof_report(
            media_path=media_path,
            output_dir=output_dir,
            start_result=start_result,
            samples=samples,
            snapshot_dir=snapshot_dir,
            started_at=started_at,
            ended_at=ended_at,
            min_pre_final_observations=min_pre_final_observations,
        )
        _write_live_nle_runtime_proof(output_dir, report)
        print(
            json.dumps(
                {
                    "ok": False,
                    "status": report.get("status"),
                    "output_dir": str(output_dir),
                    "report_path": str(output_dir / "live_nle_runtime_proof.json"),
                    "markdown_path": str(output_dir / "live_nle_runtime_proof.md"),
                    "issues": report.get("issues", []),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    deadline = time.monotonic() + max_duration_sec
    started_monotonic = time.monotonic()
    next_snapshot_at = started_monotonic
    snapshot_index = 0
    poll_index = 0
    while time.monotonic() < deadline:
        before = time.monotonic()
        try:
            status = _send("guided-subtitle-status", timeout=status_timeout)
        except OSError as exc:
            status = {"ok": False, "error": "app_unreachable", "message": str(exc), "data": {}}
        now = time.monotonic()
        sample = _live_nle_sample_from_status(
            status,
            elapsed_sec=now - started_monotonic,
            latency_sec=now - before,
            command="guided-subtitle-status",
            poll_index=poll_index,
        )
        samples.append(sample)
        poll_index += 1

        if bool(args.capture_snapshots) and now >= next_snapshot_at:
            snapshot_label = f"live_nle_{snapshot_index:02d}_{int(sample['elapsed_sec'] * 1000):06d}ms"
            _capture_snapshot(snapshot_dir, snapshot_label, timeout=status_timeout)
            snapshot_index += 1
            next_snapshot_at = now + max(1.0, float(args.snapshot_interval_sec or 5.0))

        observed, _, missing, insufficient = _pre_final_observation_summary(
            samples,
            min_observations=min_pre_final_observations,
        )
        required_seen = bool(observed) and not missing and not insufficient
        completed = bool(sample.get("generation_completed"))
        if completed and required_seen:
            break
        if completed and not bool(args.wait_after_completion):
            break
        time.sleep(poll_sec)

    ended_at = time.strftime("%Y-%m-%d %H:%M:%S")
    report = _build_live_nle_runtime_proof_report(
        media_path=media_path,
        output_dir=output_dir,
        start_result=start_result,
        samples=samples,
        snapshot_dir=snapshot_dir,
        started_at=started_at,
        ended_at=ended_at,
        min_pre_final_observations=min_pre_final_observations,
    )
    _write_live_nle_runtime_proof(output_dir, report)
    print(
        json.dumps(
            {
                "ok": report.get("status") == "passed",
                "status": report.get("status"),
                "output_dir": str(output_dir),
                "report_path": str(output_dir / "live_nle_runtime_proof.json"),
                "markdown_path": str(output_dir / "live_nle_runtime_proof.md"),
                "issues": report.get("issues", []),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report.get("status") == "passed" else 1


def _capture_snapshot(output_dir: Path, label: str, *, timeout: float) -> dict[str, Any]:
    filename = f"{label}.png"
    target = output_dir / filename
    try:
        result = _send("capture-snapshot", timeout=timeout, path=str(target))
    except OSError as exc:
        return {"ok": False, "error": "app_unreachable", "message": str(exc), "path": str(target)}
    data = dict(result.get("data") or {})
    snapshot_path = str(data.get("path", target))
    if result.get("ok") and (result.get("queued") or result.get("message") == "snapshot_queued"):
        _wait_for_snapshot(snapshot_path, timeout_sec=max(4.0, timeout))
    state = _file_state(snapshot_path)
    return {
        "ok": bool(result.get("ok")) and bool(state.get("path_exists")) and int(state.get("path_size", 0) or 0) > 0,
        "error": str(result.get("error", "") or ""),
        "message": str(result.get("message", "") or ""),
        **state,
    }


def _record_step(
    report: dict[str, Any],
    output_dir: Path,
    step_name: str,
    *,
    timeout: float,
    snapshot: bool,
    command: str | None = None,
    path: str = "",
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": step_name,
        "command": command or "",
        "path": path,
        "options": dict(options or {}),
    }
    if command:
        # 편집 명령은 UI 상태를 바꾸므로 재시도하지 않는다.
        # 대신 직전에 status fast-path로 app bridge 준비 상태를 확인해 중복 실행 위험을 피한다.
        entry["preflight_status"] = _capture_status(max(1.0, min(float(timeout or 1.0), 4.0)))
        command_started = time.monotonic()
        try:
            entry["result"] = _send(command, timeout=timeout, path=path, options=options)
        except OSError as exc:
            entry["result"] = {"ok": False, "error": "app_unreachable", "message": str(exc), "data": {}}
        entry["command_elapsed_sec"] = round(time.monotonic() - command_started, 6)
        artifact_paths = [path] if path else []
        artifact_paths.extend(_result_artifact_paths(command, entry.get("result")))
        if artifact_paths:
            # QA hot path: command success is not enough for capture/export
            # steps; the artifact must exist so false passes do not hide UI loss.
            if command in _EDITOR_SEQUENCE_ARTIFACT_COMMANDS:
                for artifact_path in artifact_paths:
                    _wait_for_snapshot(artifact_path, timeout_sec=max(4.0, timeout))
            artifacts = [_file_state(artifact_path) for artifact_path in artifact_paths]
            if len(artifacts) == 1:
                entry.update(artifacts[0])
            entry["artifacts"] = artifacts
            if command in _EDITOR_SEQUENCE_ARTIFACT_COMMANDS:
                result = dict(entry.get("result") or {})
                missing = [
                    artifact
                    for artifact in artifacts
                    if not artifact["path_exists"] or int(artifact["path_size"] or 0) <= 0
                ]
                if bool(result.get("ok")) and missing:
                    result["ok"] = False
                    result["error"] = "artifact_missing"
                    result["message"] = ", ".join(str(item.get("path", "")) for item in missing)
                    entry["result"] = result
    else:
        entry["result"] = {"ok": True, "message": "record_only", "data": {}}
    entry["status"] = _capture_status(
        _bounded_probe_timeout(timeout, cap=_EDITOR_SEQUENCE_POST_STEP_STATUS_TIMEOUT_SEC)
    )
    if snapshot:
        entry["snapshot"] = _capture_snapshot(
            output_dir,
            _safe_slug(step_name),
            timeout=_bounded_probe_timeout(timeout, cap=_EDITOR_SEQUENCE_SNAPSHOT_TIMEOUT_SEC),
        )
    report.setdefault("steps", []).append(entry)
    _write_report_files(output_dir, report)
    return entry


def _step_app_unreachable(entry: dict[str, Any] | None) -> bool:
    if not isinstance(entry, dict):
        return False
    result = entry.get("result") if isinstance(entry.get("result"), dict) else {}
    return str(result.get("error", "") or "") == "app_unreachable"


def _selection_options(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "line": args.select_line,
        "start_sec": args.select_start_sec,
        "at_playhead": bool(args.select_at_playhead),
        "center": bool(args.select_center),
        "sync_playhead": bool(args.select_sync_playhead),
    }


def _action_snapshot_path(output_dir: Path, action: str) -> str:
    return str(output_dir / f"{_safe_slug(action)}.png")


def _editor_action_spec(
    action: str,
    args: argparse.Namespace,
    selection: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any] | None:
    if action == "snapshot":
        return {"command": "", "options": {}, "snapshot": True, "path": ""}
    selection_commands = {
        "smart-split": "editor-smart-split",
        "begin-smart-split": "editor-begin-smart-split",
        "move-segment-left": "editor-move-segment-left",
        "move-segment-right": "editor-move-segment-right",
    }
    if action in selection_commands:
        return {"command": selection_commands[action], "options": dict(selection), "snapshot": False, "path": ""}
    if action == "set-inline-cursor":
        return {"command": "editor-set-inline-cursor", "options": {"position": args.cursor_pos}, "snapshot": False, "path": ""}
    if action == "commit-inline-edit":
        return {"command": "editor-commit-inline-edit", "options": {}, "snapshot": False, "path": ""}
    if action in {"play", "playback-play"}:
        return {"command": "editor-playback", "options": {"action": "play"}, "snapshot": False, "path": ""}
    if action in {"pause", "playback-pause"}:
        return {"command": "editor-playback", "options": {"action": "pause"}, "snapshot": False, "path": ""}
    timeline_actions = {
        "timeline-zoom-in": "zoom-in",
        "zoom-in": "zoom-in",
        "timeline-zoom-out": "zoom-out",
        "zoom-out": "zoom-out",
        "timeline-fit": "fit",
        "timeline-time-window": "time-window",
        "time-window": "time-window",
        "timeline-max": "max",
    }
    if action in timeline_actions:
        return {
            "command": "editor-timeline-view",
            "options": {"action": timeline_actions[action]},
            "snapshot": False,
            "path": "",
        }
    if action in {"zoom-max", "editor-zoom-max"}:
        return {"command": "editor-zoom-max", "options": {}, "snapshot": False, "path": ""}
    if action in {"start-current-pipeline", "start-pipeline", "start-generation"}:
        return {"command": "start-current-pipeline", "options": {}, "snapshot": False, "path": ""}
    if action in {"status", "status-probe"}:
        return {"command": "status", "options": {}, "snapshot": False, "path": ""}
    if action in {"guided-status", "guided-status-probe", "guided-subtitle-status"}:
        return {"command": "guided-subtitle-status", "options": {}, "snapshot": False, "path": ""}
    if action in {"save", "save-project"}:
        return {"command": "save-project", "options": {}, "snapshot": False, "path": ""}
    if action in {"cancel-current-pipeline", "cancel-pipeline"}:
        return {"command": "cancel-current-pipeline", "options": {}, "snapshot": False, "path": ""}
    if action in {"app-close-request", "close-window", "close-app"}:
        return {"command": "app-close-request", "options": {}, "snapshot": False, "path": ""}
    if action in {"app-quit-request", "quit-app"}:
        return {"command": "app-quit-request", "options": {}, "snapshot": False, "path": ""}
    if action == "save-subtitles":
        return {"command": "save-subtitles", "options": {}, "snapshot": False, "path": "", "timeout": max(float(args.timeout or 0.0), 60.0)}
    if action == "export-subtitles":
        return {
            "command": "export-subtitles",
            "options": {},
            "snapshot": False,
            "path": str(output_dir / "manual_export.srt"),
            "timeout": max(float(args.timeout or 0.0), 60.0),
        }
    if action == "export-subtitle-video":
        return {"command": "export-subtitle-video", "options": {}, "snapshot": False, "path": "", "timeout": max(float(args.timeout or 0.0), 240.0)}
    if action in {"video-show", "video-hide", "video-toggle"}:
        return {
            "command": "editor-video",
            "options": {"action": action.split("-", 1)[1]},
            "snapshot": False,
            "path": "",
        }
    if action in {"stt-enable", "stt-disable", "stt-toggle"}:
        return {
            "command": "editor-stt-mode",
            "options": {"action": action.split("-", 1)[1]},
            "snapshot": False,
            "path": "",
        }
    if action in {"open-dictionary", "open-settings", "open-speaker-settings", "close-active-dialog"}:
        return {"command": action, "options": {}, "snapshot": False, "path": ""}
    if action == "capture-active-dialog":
        return {
            # 팝업 증거는 전체 창 스냅샷과 분리해 단계별 PNG를 남긴다.
            "command": "capture-active-dialog",
            "options": {},
            "snapshot": False,
            "path": _action_snapshot_path(output_dir, action),
        }
    if action in {"capture-dictionary", "capture-dictionary-snapshot"}:
        return {
            "command": "capture-dictionary-snapshot",
            "options": {},
            "snapshot": False,
            "path": _action_snapshot_path(output_dir, "capture-dictionary"),
        }
    if action in {"lora-run-now", "lora-pause", "lora-resume"}:
        return {
            "command": "personalization-idle",
            "options": {"action": action.split("-", 1)[1]},
            "snapshot": False,
            "path": "",
        }
    if action in {"move-diamond", "merge-diamond"}:
        options = dict(selection)
        options["side"] = str(args.diamond_side or "closest")
        command = "editor-move-diamond" if action == "move-diamond" else "editor-merge-diamond"
        return {"command": command, "options": options, "snapshot": False, "path": ""}
    return None


def _editor_wait_seconds(action: str, args: argparse.Namespace) -> float | None:
    normalized = str(action or "").strip().lower()
    if normalized in {"wait", "sleep"}:
        return max(0.0, float(args.settle_sec or 0.0))
    for prefix in ("wait-", "sleep-"):
        if normalized.startswith(prefix):
            raw = normalized[len(prefix) :].strip()
            try:
                return max(0.0, float(raw))
            except ValueError:
                return None
    return None


def _record_wait_action(
    report: dict[str, Any],
    output_dir: Path,
    action: str,
    *,
    args: argparse.Namespace,
) -> None:
    wait_sec = _editor_wait_seconds(action, args)
    if wait_sec is None:
        return
    started = time.monotonic()
    time.sleep(wait_sec)
    entry: dict[str, Any] = {
        "name": action,
        "command": "",
        "path": "",
        "options": {"duration_sec": wait_sec},
        "result": {"ok": True, "message": "waited", "data": {"duration_sec": wait_sec}},
        "elapsed_sec": round(time.monotonic() - started, 6),
        "status": _capture_status(_bounded_probe_timeout(args.timeout, cap=_EDITOR_SEQUENCE_POST_STEP_STATUS_TIMEOUT_SEC)),
    }
    if args.snapshot_each_step:
        entry["snapshot"] = _capture_snapshot(
            output_dir,
            _safe_slug(action),
            timeout=_bounded_probe_timeout(args.timeout, cap=_EDITOR_SEQUENCE_SNAPSHOT_TIMEOUT_SEC),
        )
    report.setdefault("steps", []).append(entry)
    _write_report_files(output_dir, report)


def _record_editor_action(
    report: dict[str, Any],
    output_dir: Path,
    action: str,
    *,
    args: argparse.Namespace,
    selection: dict[str, Any],
) -> None:
    if _editor_wait_seconds(action, args) is not None:
        _record_wait_action(report, output_dir, action, args=args)
        return
    spec = _editor_action_spec(action, args, selection, output_dir)
    if spec is None:
        report.setdefault("steps", []).append(
            {
                "name": action,
                "command": "",
                "result": {"ok": False, "error": "unknown_action", "message": action, "data": {}},
            }
        )
        return
    if bool(spec.get("snapshot")):
        _record_step(report, output_dir, action, timeout=args.timeout, snapshot=True)
        return
    _record_step(
        report,
        output_dir,
        action,
        timeout=float(spec.get("timeout", args.timeout) or args.timeout),
        snapshot=args.snapshot_each_step,
        command=str(spec.get("command", "") or ""),
        path=str(spec.get("path", "") or ""),
        options=dict(spec.get("options") or {}),
    )


def _write_report_files(output_dir: Path, report: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "report.json"
    md_path = output_dir / "report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# Remote Verify Report",
        "",
        f"- started_at: {report.get('started_at', '')}",
        f"- output_dir: {output_dir}",
        "",
    ]
    final_status = dict(report.get("final_status") or {})
    runtime = dict((final_status.get("data") or {}).get("editor_runtime") or {})
    if runtime:
        lines.extend(
            [
                "## Final Runtime",
                "",
                f"- playhead_sec: {runtime.get('playhead_sec')}",
                f"- active_seg_line: {runtime.get('active_seg_line')}",
                f"- active_seg_start: {runtime.get('active_seg_start')}",
                f"- segment_count: {runtime.get('segment_count')}",
                "",
            ]
        )
    lines.append("## Steps")
    lines.append("")
    for step in list(report.get("steps") or []):
        result = dict(step.get("result") or {})
        snapshot = dict(step.get("snapshot") or {})
        lines.append(f"- {step.get('name')}: ok={result.get('ok')} command={step.get('command')}")
        if snapshot:
            lines.append(f"  snapshot: {snapshot.get('path')}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_editor_sequence(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir).resolve() if args.output_dir else _default_output_dir(args.label or "remote_verify")
    output_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "output_dir": str(output_dir),
        "steps": [],
    }

    open_target = ""
    open_command = ""
    if args.open_media:
        open_command, open_target = "open-media", str(Path(args.open_media).resolve())
    elif args.open_srt:
        open_command, open_target = "open-srt", str(Path(args.open_srt).resolve())
    elif args.open_project:
        open_command, open_target = "open-project", str(Path(args.open_project).resolve())

    if open_command:
        open_entry = _record_step(
            report,
            output_dir,
            "open",
            timeout=args.timeout,
            snapshot=args.snapshot_each_step,
            command=open_command,
            path=open_target,
        )
        if _step_app_unreachable(open_entry):
            report["aborted"] = True
            report["abort_reason"] = "open_app_unreachable"
            report["final_status"] = _capture_status(
                _bounded_probe_timeout(args.timeout, cap=_EDITOR_SEQUENCE_POST_STEP_STATUS_TIMEOUT_SEC)
            )
            _write_report_files(output_dir, report)
            print(
                json.dumps(
                    {
                        "ok": False,
                        "output_dir": str(output_dir),
                        "report_path": str(output_dir / "report.json"),
                        "abort_reason": report["abort_reason"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1
        time.sleep(max(0.0, float(args.settle_sec or 0.0)))

    _record_step(report, output_dir, "initial", timeout=args.timeout, snapshot=args.snapshot_each_step)

    if args.playhead_sec is not None:
        _record_step(
            report,
            output_dir,
            "set-playhead",
            timeout=args.timeout,
            snapshot=args.snapshot_each_step,
            command="editor-set-playhead",
            options={
                "sec": float(args.playhead_sec),
                "center": bool(args.playhead_center),
                "sync_video": not bool(args.no_sync_video),
            },
        )

    selection = _selection_options(args)
    if selection.get("line") is not None or selection.get("start_sec") is not None or selection.get("at_playhead"):
        _record_step(
            report,
            output_dir,
            "select-segment",
            timeout=args.timeout,
            snapshot=args.snapshot_each_step,
            command="editor-select-segment",
            options=selection,
        )

    for raw_action in list(args.actions or []):
        action = str(raw_action or "").strip().lower()
        if not action:
            continue
        _record_editor_action(report, output_dir, action, args=args, selection=selection)

    report["final_status"] = _capture_status(args.timeout)
    _write_report_files(output_dir, report)
    print(json.dumps({"ok": True, "output_dir": str(output_dir), "report_path": str(output_dir / "report.json")}, ensure_ascii=False, indent=2))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run remote app verification scenarios and save report artifacts.")
    parser.add_argument("--timeout", type=float, default=8.0)
    sub = parser.add_subparsers(dest="command", required=True)

    capture = sub.add_parser("capture")
    capture.add_argument("--label", default="capture")
    capture.add_argument("--output-dir", default="")

    editor = sub.add_parser("editor-sequence")
    editor.add_argument("--label", default="editor_sequence")
    editor.add_argument("--output-dir", default="")
    editor.add_argument("--open-media", default="")
    editor.add_argument("--open-srt", default="")
    editor.add_argument("--open-project", default="")
    editor.add_argument("--settle-sec", type=float, default=0.35)
    editor.add_argument("--playhead-sec", type=float, default=None)
    editor.add_argument("--playhead-center", action="store_true")
    editor.add_argument("--no-sync-video", action="store_true")
    editor.add_argument("--select-line", type=int, default=None)
    editor.add_argument("--select-start-sec", type=float, default=None)
    editor.add_argument("--select-at-playhead", action="store_true")
    editor.add_argument("--select-center", action="store_true")
    editor.add_argument("--select-sync-playhead", action="store_true")
    editor.add_argument("--cursor-pos", type=int, default=None)
    editor.add_argument("--diamond-side", choices=["left", "right", "closest"], default="closest")
    editor.add_argument(
        "--actions",
        nargs="*",
        default=[],
        help="Supported: begin-smart-split set-inline-cursor commit-inline-edit smart-split play pause timeline-zoom-in timeline-zoom-out timeline-fit timeline-time-window timeline-max zoom-max start-current-pipeline status-probe guided-status-probe wait-N save-project cancel-current-pipeline app-close-request app-quit-request save-subtitles export-subtitles export-subtitle-video move-segment-left move-segment-right move-diamond merge-diamond video-show video-hide video-toggle stt-enable stt-disable stt-toggle open-dictionary open-settings open-speaker-settings capture-active-dialog capture-dictionary close-active-dialog lora-run-now lora-pause lora-resume snapshot",
    )
    editor.add_argument("--snapshot-each-step", action="store_true")

    live_nle = sub.add_parser("live-nle-proof")
    live_nle.add_argument("--label", default="live_nle_runtime_proof")
    live_nle.add_argument("--output-dir", default="")
    live_nle.add_argument("--media", required=True)
    live_nle.add_argument("--start-timeout", type=float, default=30.0)
    live_nle.add_argument("--poll-sec", type=float, default=1.0)
    live_nle.add_argument("--max-duration-sec", type=float, default=180.0)
    live_nle.add_argument(
        "--min-pre-final-observations",
        type=int,
        default=_LIVE_NLE_DEFAULT_MIN_PRE_FINAL_OBSERVATIONS,
    )
    live_nle.add_argument("--capture-snapshots", action="store_true")
    live_nle.add_argument("--snapshot-interval-sec", type=float, default=5.0)
    live_nle.add_argument("--wait-after-completion", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "capture":
        output_dir = Path(args.output_dir).resolve() if args.output_dir else _default_output_dir(args.label or "capture")
        output_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "output_dir": str(output_dir),
            "status": _capture_status(args.timeout),
            "snapshot": _capture_snapshot(output_dir, _safe_slug(args.label), timeout=args.timeout),
        }
        _write_report_files(output_dir, {"started_at": report["started_at"], "steps": [], "final_status": report["status"]})
        (output_dir / "capture.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": True, "output_dir": str(output_dir), "capture_path": str(output_dir / "capture.json")}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "editor-sequence":
        return _run_editor_sequence(args)
    if args.command == "live-nle-proof":
        return _run_live_nle_proof(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
