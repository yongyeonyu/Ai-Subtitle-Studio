import json
import tempfile
from pathlib import Path

from tools.audit_g3_active_final_surface import build_report, write_report


def _budget_contract(ok: bool = True) -> dict:
    return {
        "present": True,
        "ok": bool(ok),
        "fields": {
            "dedicated_worker_count": 0,
            "max_projection_workers": 0,
            "shares_subtitle_worker_pool": False,
            "uses_existing_row_snapshots": True,
            "coalesces_updates": True,
            "drops_stale_preview_frames": True,
            "quality_policy": "final_authority_unchanged",
        },
    }


def _compact_contract(*, authority_drift: bool = False, raw_leak: bool = False) -> dict:
    return {
        "compact_payload": True,
        "raw_payload_leak": bool(raw_leak),
        "authority": {
            "VAD": False,
            "STT1": bool(authority_drift),
            "STT2": False,
            "subtitle_preview": False,
            "final": True,
        },
        "role": {
            "VAD": "runtime_reference_only",
            "STT1": "runtime_reference_only",
            "STT2": "runtime_reference_only",
            "subtitle_preview": "runtime_reference_only",
            "final": "save_export_render_authority",
        },
        "final_authority_ok": not authority_drift,
    }


def _sample(
    poll_index: int,
    *,
    elapsed_sec: float,
    final_count: int,
    completed: bool = False,
    cached: bool = False,
    timeout: bool = False,
    fallback: bool = False,
    authority_drift: bool = False,
    raw_leak: bool = False,
    budget_ok: bool = True,
) -> dict:
    return {
        "command": "guided-subtitle-status",
        "poll_index": poll_index,
        "elapsed_sec": elapsed_sec,
        "latency_sec": 0.01,
        "ok": True,
        "error": "",
        "status_handler_timeout": bool(timeout),
        "status_response_cached": bool(cached),
        "status_snapshot_fallback": bool(fallback),
        "status_response_truncated": True,
        "editor_state": "ST_PROC" if not completed else "READY",
        "backend_active": not completed,
        "auto_processing_active": not completed,
        "guided_active": not completed,
        "last_stage_key": "subtitle-generation" if not completed else "completed",
        "generation_stage": "active final stage",
        "subtitle_count": final_count,
        "nle_runtime_track_counts": {
            "VAD": 0,
            "STT1": 12,
            "STT2": 3,
            "subtitle_preview": 2,
            "final": final_count,
        },
        "pre_final_active": not completed,
        "generation_completed": bool(completed),
        "compact_runtime_track_contract": _compact_contract(
            authority_drift=authority_drift,
            raw_leak=raw_leak,
        ),
        "live_nle_projection_budget_contract": _budget_contract(ok=budget_ok),
    }


def _write_fixture(
    root: Path,
    *,
    samples: list[dict],
    proof_updates: dict | None = None,
    snapshot_ms: int = 107317,
) -> None:
    (root / "snapshots").mkdir(parents=True)
    snapshot = root / "snapshots" / f"live_nle_13_{snapshot_ms:06d}ms.png"
    snapshot.write_bytes(b"png")
    proof = {
        "schema": "ai_subtitle_studio.live_nle_runtime_proof.v2",
        "status": "passed",
        "sample_count": len(samples),
        "failed_sample_count": 0,
        "generation_completed": True,
        "issues": [],
        "raw_payload_leak_elapsed_sec": [],
        "compact_payload_failure_elapsed_sec": [],
        "final_authority_failure_elapsed_sec": [],
        "budget_failure_elapsed_sec": [],
        "status_handler_timeout_elapsed_sec": [],
        "status_response_cached_elapsed_sec": [],
        "status_snapshot_fallback_elapsed_sec": [],
        "snapshot_files": [f"snapshots/{snapshot.name}"],
    }
    proof.update(proof_updates or {})
    (root / "live_nle_runtime_proof.json").write_text(json.dumps(proof), encoding="utf-8")
    (root / "status_samples.json").write_text(json.dumps(samples), encoding="utf-8")


def test_active_final_surface_audit_passes_with_pre_final_final_track_and_exact_snapshot():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_fixture(
            root,
            samples=[
                _sample(203, elapsed_sec=106.774, final_count=47),
                _sample(204, elapsed_sec=107.317, final_count=47),
                _sample(205, elapsed_sec=123.452, final_count=64, completed=True),
            ],
        )

        report = build_report(source_dir=root, output_dir=root)
        write_report(report, root)

    assert report["status"] == "passed"
    assert report["valid_active_final_observation_count"] == 2
    assert report["snapshot_pair_count"] == 1
    assert report["max_counts"]["final"] == 47
    assert report["raw_payload_guard_source"] == "derived_compact_contract_flags_and_source_summary_failure_lists"
    assert report["issues"] == []


def test_active_final_surface_audit_blocks_completed_only_final_samples():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_fixture(root, samples=[_sample(205, elapsed_sec=107.317, final_count=64, completed=True)])

        report = build_report(source_dir=root, output_dir=root)

    assert report["status"] == "blocked"
    assert "insufficient_active_final_observations" in report["issues"]
    assert report["valid_active_final_observation_count"] == 0


def test_active_final_surface_audit_blocks_drift_and_missing_snapshot_pair():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_fixture(
            root,
            samples=[
                _sample(203, elapsed_sec=106.774, final_count=47, authority_drift=True),
                _sample(204, elapsed_sec=107.317, final_count=47, raw_leak=True),
                _sample(205, elapsed_sec=108.0, final_count=47, budget_ok=False),
            ],
            proof_updates={
                "raw_payload_leak_elapsed_sec": [107.317],
                "final_authority_failure_elapsed_sec": [106.774],
                "budget_failure_elapsed_sec": [108.0],
                "snapshot_files": [],
            },
        )

        report = build_report(source_dir=root, output_dir=root)

    assert report["status"] == "blocked"
    assert "source_raw_payload_leak" in report["issues"]
    assert "source_final_authority_failure" in report["issues"]
    assert "source_budget_failure" in report["issues"]
    assert "insufficient_active_final_observations" in report["issues"]
    assert "active_final_snapshot_pair_missing" in report["issues"]
