#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.subtitle_benchmark_scoring import clip_reference, parse_srt  # noqa: E402

DEFAULT_HEYDEALER_MEDIA = Path(
    "/Volumes/photo/22_유튜브영상_개인/[20260209]헤이딜러광고/헤이딜러_최종.MP4"
)
DEFAULT_HEYDEALER_REFERENCE = Path(
    "/Volumes/photo/22_유튜브영상_개인/[20260209]헤이딜러광고/헤이딜러_최종.srt"
)


def _path_status(path: Path) -> dict[str, Any]:
    resolved = path.expanduser()
    exists = resolved.exists()
    stat_size = None
    if exists and resolved.is_file():
        try:
            stat_size = resolved.stat().st_size
        except OSError:
            stat_size = None
    return {
        "path": str(resolved),
        "exists": exists,
        "is_file": exists and resolved.is_file(),
        "size_bytes": stat_size,
    }


def _reference_status(path: Path, *, start_sec: float, duration_sec: float) -> dict[str, Any]:
    status = _path_status(path)
    status["parse_ok"] = False
    status["segment_count"] = 0
    status["clipped_segment_count"] = 0
    status["parse_error"] = ""
    if not bool(status.get("is_file")):
        return status
    try:
        rows = parse_srt(path.expanduser())
        clipped = clip_reference(rows, start_sec, start_sec + max(1.0, duration_sec))
        status["parse_ok"] = True
        status["segment_count"] = len(rows)
        status["clipped_segment_count"] = len(clipped)
    except Exception as exc:
        status["parse_error"] = str(exc)
    return status


def build_availability_report(
    *,
    media: Path,
    reference_srt: Path,
    fallback_media: list[Path] | None = None,
    start_sec: float = 0.0,
    duration_sec: float = 180.0,
) -> dict[str, Any]:
    media_status = _path_status(media)
    reference_status = _reference_status(reference_srt, start_sec=start_sec, duration_sec=duration_sec)
    fallback_statuses = [_path_status(path) for path in list(fallback_media or [])]
    available_fallbacks = [item for item in fallback_statuses if bool(item.get("is_file"))]

    blockers: list[str] = []
    if not bool(media_status.get("is_file")):
        blockers.append("reference_media_missing")
    if not bool(reference_status.get("is_file")):
        blockers.append("reference_srt_missing")
    elif not bool(reference_status.get("parse_ok")):
        blockers.append("reference_srt_parse_failed")
    elif int(reference_status.get("clipped_segment_count") or 0) <= 0:
        blockers.append("reference_srt_has_no_segments_in_window")

    ready = not blockers
    benchmark_command = ""
    if ready:
        benchmark_command = (
            "QT_QPA_PLATFORM=offscreen ./venv/bin/python "
            "tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high "
            f"--media {json.dumps(str(media.expanduser()), ensure_ascii=False)} "
            f"--reference-srt {json.dumps(str(reference_srt.expanduser()), ensure_ascii=False)} "
            f"--start-sec {float(start_sec):g} --duration-sec {float(duration_sec):g} --keep-artifacts"
        )

    return {
        "schema": "ai_subtitle_studio.reference_fixture_availability.v1",
        "ready_for_reference_scored_benchmark": ready,
        "blocking_reasons": blockers,
        "media": media_status,
        "reference_srt": reference_status,
        "fallback_media": fallback_statuses,
        "non_reference_media_available": bool(available_fallbacks),
        "non_reference_warning": (
            "Fallback media can prove instrumentation and structural stability only; it must not approve latency trims."
            if available_fallbacks and not ready
            else ""
        ),
        "start_sec": float(start_sec),
        "duration_sec": float(duration_sec),
        "benchmark_command": benchmark_command,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _markdown_report(payload: dict[str, Any]) -> str:
    blockers = list(payload.get("blocking_reasons") or [])
    lines = [
        "# Reference Fixture Availability",
        "",
        f"- Ready for reference-scored benchmark: `{bool(payload.get('ready_for_reference_scored_benchmark'))}`",
        f"- Blocking reasons: `{', '.join(str(item) for item in blockers) if blockers else 'none'}`",
        f"- Media: `{(payload.get('media') or {}).get('path')}`",
        f"- Media exists: `{(payload.get('media') or {}).get('is_file')}`",
        f"- Reference SRT: `{(payload.get('reference_srt') or {}).get('path')}`",
        f"- Reference SRT exists: `{(payload.get('reference_srt') or {}).get('is_file')}`",
        f"- Reference clipped segments: `{(payload.get('reference_srt') or {}).get('clipped_segment_count')}`",
        f"- Non-reference fallback available: `{bool(payload.get('non_reference_media_available'))}`",
    ]
    warning = str(payload.get("non_reference_warning") or "").strip()
    if warning:
        lines.extend(["", f"Warning: {warning}"])
    command = str(payload.get("benchmark_command") or "").strip()
    if command:
        lines.extend(["", "## Command", "", "```bash", command, "```"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether a real-media reference benchmark fixture is available.")
    parser.add_argument("--media", default=str(DEFAULT_HEYDEALER_MEDIA))
    parser.add_argument("--reference-srt", default=str(DEFAULT_HEYDEALER_REFERENCE))
    parser.add_argument("--fallback-media", action="append", default=[])
    parser.add_argument("--start-sec", type=float, default=0.0)
    parser.add_argument("--duration-sec", type=float, default=180.0)
    parser.add_argument("--output-dir", default="output/manual_verification/latest/reference_fixture_availability")
    args = parser.parse_args()

    payload = build_availability_report(
        media=Path(args.media),
        reference_srt=Path(args.reference_srt),
        fallback_media=[Path(item) for item in list(args.fallback_media or [])],
        start_sec=max(0.0, float(args.start_sec or 0.0)),
        duration_sec=max(1.0, float(args.duration_sec or 180.0)),
    )
    output_dir = Path(args.output_dir).expanduser()
    _write_json(output_dir / "reference_fixture_availability.json", payload)
    _write_text(output_dir / "reference_fixture_availability.md", _markdown_report(payload))
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if bool(payload.get("ready_for_reference_scored_benchmark")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
