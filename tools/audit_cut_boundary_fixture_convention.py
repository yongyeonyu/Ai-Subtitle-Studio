#!/usr/bin/env python3
"""Create visual fixture evidence for cut-boundary frame convention review."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.native_json import dumps_json_bytes
from tools.audit_cut_boundary_frame_semantics import DEFAULT_BLOCKED_RUNTIME_CHANGES


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _pair_label(pair: dict[str, Any]) -> str:
    return f"{_as_int(pair.get('left_frame'))}->{_as_int(pair.get('right_frame'))}"


def _metric_summary(metrics: dict[str, Any] | None) -> dict[str, Any]:
    metrics = metrics or {}
    return {
        "available": bool(metrics.get("available")),
        "left_frame": _as_int(metrics.get("left_frame")),
        "right_frame": _as_int(metrics.get("right_frame")),
        "mean_abs_delta": round(_as_float(metrics.get("mean_abs_delta")), 6),
        "max_abs_delta": round(_as_float(metrics.get("max_abs_delta")), 6),
        "changed_pixel_ratio": round(_as_float(metrics.get("changed_pixel_ratio")), 6),
        "missing_reason": str(metrics.get("missing_reason") or ""),
    }


def _window_convention_row(
    window: dict[str, Any],
    *,
    pair_metrics: dict[str, Any] | None = None,
    contact_sheet_path: str = "",
) -> dict[str, Any]:
    target = _as_int(window.get("target_frame"))
    expected = dict(window.get("expected_transition") or {})
    strongest = dict(window.get("strongest_transition") or {})
    classification = str(window.get("classification") or "")
    label_review_required = classification in {"detected_neighbor_before_target", "detected_neighbor_after_target"}
    detector_evidence_required = bool(window.get("target_detection_gap")) and not label_review_required
    pair_metrics = pair_metrics or {}
    expected_metrics = _metric_summary(pair_metrics.get("expected_pair_metrics"))
    strongest_metrics = _metric_summary(pair_metrics.get("strongest_pair_metrics"))
    expected_delta = _as_float(expected_metrics.get("mean_abs_delta"))
    strongest_delta = _as_float(strongest_metrics.get("mean_abs_delta"))
    delta_ratio = round(strongest_delta / expected_delta, 6) if expected_delta > 0.0 else 0.0
    if label_review_required:
        next_action = "verify_fixture_label_or_boundary_frame_convention_before_threshold_tuning"
    elif detector_evidence_required:
        next_action = "improve_detector_evidence_or_fixture_truth_before_threshold_tuning"
    else:
        next_action = "no_fixture_convention_review_required"
    return {
        "target_frame": target,
        "classification": classification,
        "expected_pair": _pair_label(expected),
        "strongest_pair": _pair_label(strongest),
        "strongest_offset_from_target": _as_int(window.get("strongest_offset_from_target")),
        "target_detected": bool(window.get("target_detected")),
        "strongest_detected": bool(window.get("strongest_detected")),
        "label_or_boundary_convention_review_required": label_review_required,
        "detector_evidence_required": detector_evidence_required,
        "expected_pair_metrics": expected_metrics,
        "strongest_pair_metrics": strongest_metrics,
        "strongest_to_expected_mean_delta_ratio": delta_ratio,
        "contact_sheet_path": contact_sheet_path,
        "next_action": next_action,
    }


def build_fixture_convention_audit(
    semantics_audit: dict[str, Any],
    *,
    pair_metrics_by_target: dict[int, dict[str, Any]] | None = None,
    contact_sheets_by_target: dict[int, str] | None = None,
    source_path: Path | None = None,
    media_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    started = time.time()
    pair_metrics_by_target = pair_metrics_by_target or {}
    contact_sheets_by_target = contact_sheets_by_target or {}
    rows: list[dict[str, Any]] = []
    for window in list(semantics_audit.get("windows") or []):
        if not isinstance(window, dict):
            continue
        target = _as_int(window.get("target_frame"))
        rows.append(
            _window_convention_row(
                window,
                pair_metrics=pair_metrics_by_target.get(target),
                contact_sheet_path=contact_sheets_by_target.get(target, ""),
            )
        )
    label_review_count = sum(1 for row in rows if row.get("label_or_boundary_convention_review_required"))
    detector_evidence_required_count = sum(1 for row in rows if row.get("detector_evidence_required"))
    blocked = list(semantics_audit.get("blocked_runtime_changes") or [])
    for item in DEFAULT_BLOCKED_RUNTIME_CHANGES:
        if item not in blocked:
            blocked.append(item)
    manifest = {
        "schema": "ai_subtitle_studio.cut_boundary_fixture_convention_audit.v1",
        "note": "Read-only audit. It materializes fixture-frame evidence for boundary-frame convention review.",
        "source_frame_semantics_audit_path": str(source_path) if source_path else "",
        "source_schema": str(semantics_audit.get("schema") or ""),
        "media_path": str(media_path or semantics_audit.get("media_path") or ""),
        "fixture_label_or_boundary_convention_review_required": bool(label_review_count),
        "label_or_boundary_convention_review_count": label_review_count,
        "detector_evidence_required_count": detector_evidence_required_count,
        "runtime_change_allowed": False,
        "blocked_runtime_changes": blocked,
        "contact_sheet_count": sum(1 for row in rows if row.get("contact_sheet_path")),
        "windows": rows,
        "elapsed_sec": round(time.time() - started, 3),
    }
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / "cut_boundary_fixture_convention_audit.json"
        md_path = output_dir / "cut_boundary_fixture_convention_audit.md"
        json_path.write_bytes(dumps_json_bytes(manifest, indent=2, sort_keys=True, append_newline=True))
        manifest["artifact_path"] = str(json_path)
        _write_markdown(md_path, manifest)
    return manifest


def _read_bgr_frames(media_path: Path, frames: list[int], *, width: int, height: int) -> dict[int, Any]:
    import cv2

    ordered = sorted(set(int(frame) for frame in frames if int(frame) >= 0))
    cap = cv2.VideoCapture(str(media_path))
    if cap is None or not cap.isOpened():
        raise RuntimeError(f"VideoCapture failed: {media_path}")
    out: dict[int, Any] = {}
    try:
        for frame_no in ordered:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            out[frame_no] = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA).copy()
    finally:
        try:
            cap.release()
        except Exception:
            pass
    return out


def _pair_metrics(frame_map: dict[int, Any], left_frame: int, right_frame: int) -> dict[str, Any]:
    import numpy as np

    left = frame_map.get(left_frame)
    right = frame_map.get(right_frame)
    if left is None or right is None:
        return {
            "available": False,
            "left_frame": left_frame,
            "right_frame": right_frame,
            "missing_reason": "missing_frame",
        }
    diff = np.abs(left.astype(np.int16) - right.astype(np.int16))
    per_pixel = diff.mean(axis=2)
    return {
        "available": True,
        "left_frame": left_frame,
        "right_frame": right_frame,
        "mean_abs_delta": float(diff.mean()),
        "max_abs_delta": float(diff.max()),
        "changed_pixel_ratio": float((per_pixel >= 16.0).mean()),
    }


def _frames_for_window(window: dict[str, Any], *, context_radius: int) -> list[int]:
    frames: set[int] = set()
    for pair_key in ("expected_transition", "strongest_transition"):
        pair = dict(window.get(pair_key) or {})
        left = _as_int(pair.get("left_frame"), -1)
        right = _as_int(pair.get("right_frame"), -1)
        for frame in (left, right):
            if frame >= 0:
                for offset in range(-context_radius, context_radius + 1):
                    candidate = frame + offset
                    if candidate >= 0:
                        frames.add(candidate)
    return sorted(frames)


def _write_contact_sheet(
    *,
    target: int,
    frames: list[int],
    frame_map: dict[int, Any],
    output_dir: Path,
) -> str:
    import cv2
    import numpy as np

    available = [frame for frame in frames if frame in frame_map]
    if not available:
        return ""
    first = frame_map[available[0]]
    tile_h, tile_w = first.shape[:2]
    label_h = 34
    canvas = np.full((tile_h + label_h, tile_w * len(available), 3), 245, dtype=np.uint8)
    for index, frame_no in enumerate(available):
        x0 = index * tile_w
        canvas[label_h : label_h + tile_h, x0 : x0 + tile_w] = frame_map[frame_no]
        cv2.putText(
            canvas,
            f"frame {frame_no}",
            (x0 + 8, 23),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (20, 20, 20),
            1,
            cv2.LINE_AA,
        )
        cv2.rectangle(canvas, (x0, label_h), (x0 + tile_w - 1, label_h + tile_h - 1), (50, 50, 50), 1)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"target_{target}_frame_contact_sheet.png"
    ok = cv2.imwrite(str(path), canvas)
    if not ok:
        raise RuntimeError(f"failed to write contact sheet: {path}")
    return str(path)


def _materialize_fixture_evidence(
    semantics_audit: dict[str, Any],
    *,
    media_path: Path,
    output_dir: Path,
    width: int,
    height: int,
    context_radius: int,
) -> tuple[dict[int, dict[str, Any]], dict[int, str]]:
    needed: set[int] = set()
    windows = [window for window in list(semantics_audit.get("windows") or []) if isinstance(window, dict)]
    for window in windows:
        needed.update(_frames_for_window(window, context_radius=context_radius))
    frame_map = _read_bgr_frames(media_path, sorted(needed), width=width, height=height)
    pair_metrics_by_target: dict[int, dict[str, Any]] = {}
    contact_sheets_by_target: dict[int, str] = {}
    for window in windows:
        target = _as_int(window.get("target_frame"))
        expected = dict(window.get("expected_transition") or {})
        strongest = dict(window.get("strongest_transition") or {})
        pair_metrics_by_target[target] = {
            "expected_pair_metrics": _pair_metrics(
                frame_map,
                _as_int(expected.get("left_frame")),
                _as_int(expected.get("right_frame")),
            ),
            "strongest_pair_metrics": _pair_metrics(
                frame_map,
                _as_int(strongest.get("left_frame")),
                _as_int(strongest.get("right_frame")),
            ),
        }
        contact_sheets_by_target[target] = _write_contact_sheet(
            target=target,
            frames=_frames_for_window(window, context_radius=context_radius),
            frame_map=frame_map,
            output_dir=output_dir,
        )
    return pair_metrics_by_target, contact_sheets_by_target


def _write_markdown(path: Path, manifest: dict[str, Any]) -> None:
    lines = [
        "# Cut Boundary Fixture Convention Audit",
        "",
        f"- Fixture convention review required: `{bool(manifest.get('fixture_label_or_boundary_convention_review_required'))}`",
        f"- Label/boundary convention review count: `{manifest.get('label_or_boundary_convention_review_count')}`",
        f"- Detector evidence required count: `{manifest.get('detector_evidence_required_count')}`",
        f"- Contact sheet count: `{manifest.get('contact_sheet_count')}`",
        f"- Runtime change allowed: `{bool(manifest.get('runtime_change_allowed'))}`",
        f"- Source semantics audit: `{manifest.get('source_frame_semantics_audit_path')}`",
        f"- Media: `{manifest.get('media_path')}`",
        "",
        "## Targets",
        "",
        "| Target | Classification | Expected pair | Strongest pair | Offset | Expected delta | Strongest delta | Ratio | Contact sheet | Next action |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in list(manifest.get("windows") or []):
        if not isinstance(row, dict):
            continue
        expected = row.get("expected_pair_metrics") or {}
        strongest = row.get("strongest_pair_metrics") or {}
        lines.append(
            "| {target} | {classification} | {expected_pair} | {strongest_pair} | {offset} | {expected_delta} | {strongest_delta} | {ratio} | {sheet} | {next_action} |".format(
                target=row.get("target_frame"),
                classification=row.get("classification"),
                expected_pair=row.get("expected_pair"),
                strongest_pair=row.get("strongest_pair"),
                offset=row.get("strongest_offset_from_target"),
                expected_delta=expected.get("mean_abs_delta"),
                strongest_delta=strongest.get("mean_abs_delta"),
                ratio=row.get("strongest_to_expected_mean_delta_ratio"),
                sheet=row.get("contact_sheet_path") or "",
                next_action=row.get("next_action"),
            )
        )
    lines.extend(["", "## Guardrails", ""])
    for item in list(manifest.get("blocked_runtime_changes") or []):
        lines.append(f"- Do not apply `{item}` from this audit alone.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize fixture-frame evidence for boundary-frame convention review.")
    parser.add_argument("frame_semantics_audit_json", type=Path)
    parser.add_argument("--media", type=Path, default=None)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=180)
    parser.add_argument("--context-radius", type=int, default=1)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source_path = args.frame_semantics_audit_json
    semantics = json.loads(source_path.read_text(encoding="utf-8"))
    media_path = args.media or Path(str(semantics.get("media_path") or ""))
    if not media_path.is_file():
        raise FileNotFoundError(media_path)
    output_dir = args.output_dir
    pair_metrics_by_target, contact_sheets_by_target = _materialize_fixture_evidence(
        semantics,
        media_path=media_path,
        output_dir=output_dir,
        width=max(64, min(960, int(args.width or 320))),
        height=max(36, min(540, int(args.height or 180))),
        context_radius=max(0, min(3, int(args.context_radius or 0))),
    )
    manifest = build_fixture_convention_audit(
        semantics,
        pair_metrics_by_target=pair_metrics_by_target,
        contact_sheets_by_target=contact_sheets_by_target,
        source_path=source_path,
        media_path=media_path,
        output_dir=output_dir,
    )
    print(dumps_json_bytes(manifest, indent=2, sort_keys=True).decode("utf-8"))
    return 1 if manifest.get("fixture_label_or_boundary_convention_review_required") else 0


if __name__ == "__main__":
    raise SystemExit(main())
