#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _format_srt_time(seconds: float) -> str:
    total_ms = max(0, int(round(float(seconds) * 1000.0)))
    hours, rem_ms = divmod(total_ms, 3_600_000)
    minutes, rem_ms = divmod(rem_ms, 60_000)
    secs, millis = divmod(rem_ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _clean_text(value: Any) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def materialize_rows_from_json(
    payload: dict[str, Any],
    *,
    source_start_sec: float | None = None,
    duration_sec: float | None = None,
) -> list[dict[str, Any]]:
    rows = list(payload.get("rows") or [])
    if source_start_sec is None:
        source_start_sec = float(payload.get("start", 0.0) or 0.0)
    if duration_sec is None:
        end = float(payload.get("end", float(source_start_sec) + 1.0) or float(source_start_sec) + 1.0)
        duration_sec = max(1.0, end - float(source_start_sec))
    source_start = max(0.0, float(source_start_sec))
    source_end = source_start + max(1.0, float(duration_sec))

    materialized: list[dict[str, Any]] = []
    for row in rows:
        absolute_start = float(row.get("start", 0.0) or 0.0)
        absolute_end = float(row.get("end", absolute_start) or absolute_start)
        if absolute_end <= source_start or absolute_start >= source_end:
            continue
        start = max(0.0, absolute_start - source_start)
        end = max(0.0, min(absolute_end, source_end) - source_start)
        text = _clean_text(row.get("text"))
        if not text or end <= start:
            continue
        materialized.append({"start": start, "end": end, "text": text})
    return materialized


def srt_text_from_rows(rows: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for idx, row in enumerate(rows, start=1):
        blocks.append(
            "\n".join(
                [
                    str(idx),
                    f"{_format_srt_time(float(row['start']))} --> {_format_srt_time(float(row['end']))}",
                    _clean_text(row.get("text")),
                ]
            )
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def build_materialization_report(
    *,
    reference_json: Path,
    output_srt: Path,
    rows: list[dict[str, Any]],
    source_start_sec: float,
    duration_sec: float,
) -> dict[str, Any]:
    return {
        "schema": "ai_subtitle_studio.materialized_reference_srt.v1",
        "reference_json": str(reference_json),
        "output_srt": str(output_srt),
        "source_start_sec": float(source_start_sec),
        "duration_sec": float(duration_sec),
        "row_count": len(rows),
        "ready_for_reference_preflight": bool(rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize cached reference JSON rows into a relative-time SRT fixture.")
    parser.add_argument("--reference-json", required=True)
    parser.add_argument("--output-srt", required=True)
    parser.add_argument("--source-start-sec", type=float, default=None)
    parser.add_argument("--duration-sec", type=float, default=None)
    parser.add_argument("--report-json", default="")
    args = parser.parse_args()

    reference_json = Path(args.reference_json).expanduser()
    payload = json.loads(reference_json.read_text(encoding="utf-8"))
    source_start = (
        float(args.source_start_sec)
        if args.source_start_sec is not None
        else float(payload.get("start", 0.0) or 0.0)
    )
    duration = (
        float(args.duration_sec)
        if args.duration_sec is not None
        else max(1.0, float(payload.get("end", source_start + 1.0) or source_start + 1.0) - source_start)
    )
    rows = materialize_rows_from_json(payload, source_start_sec=source_start, duration_sec=duration)

    output_srt = Path(args.output_srt).expanduser()
    output_srt.parent.mkdir(parents=True, exist_ok=True)
    output_srt.write_text(srt_text_from_rows(rows), encoding="utf-8")
    report = build_materialization_report(
        reference_json=reference_json,
        output_srt=output_srt,
        rows=rows,
        source_start_sec=source_start,
        duration_sec=duration,
    )
    if args.report_json:
        report_path = Path(args.report_json).expanduser()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if rows else 2


if __name__ == "__main__":
    raise SystemExit(main())
