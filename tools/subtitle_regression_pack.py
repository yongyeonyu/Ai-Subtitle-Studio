from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.media_info import probe_media  # noqa: E402
from core.project.project_assets import externalize_project_text_assets  # noqa: E402
from core.project.project_context import build_editor_state, project_segments_to_editor  # noqa: E402
from core.project.project_io import clear_project_file_cache, write_project_file  # noqa: E402
from core.project.project_manager import load_project  # noqa: E402
from tools.benchmark_subtitle_pipeline_variants import score_readability  # noqa: E402
from tools.verify_full_media_pipeline import run_full_verification  # noqa: E402

DEFAULT_TINYPING_MEDIA = Path("/Users/u_mo_c/Downloads/티니핑/티니핑_유스어드벤처.MP4")
DEFAULT_TINYPING_REFERENCE = Path("/Users/u_mo_c/Downloads/티니핑/티니핑_유스어드벤처_완성.srt")
DEFAULT_X5_MEDIA = ROOT / "test video" / "X5_시승기_후반.MP4"
DEFAULT_X5_REFERENCE = ROOT / "test video" / "X5_시승기_후반.srt"
DEFAULT_MACAU_MEDIA = Path("/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217224203_0075_D.MP4")
DEFAULT_REGRESSION_PACK_DIR = ROOT / "output" / "manual_verification" / "latest" / "subtitle_regression_pack"
REGRESSION_FIXTURE_KEYS = ("x5", "macau", "tinyping_short", "tinyping_full")


def _json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_regression_fixtures(raw: str) -> list[str]:
    wanted = [item.strip().lower() for item in str(raw or "").split(",") if item.strip()]
    if not wanted:
        return list(REGRESSION_FIXTURE_KEYS)
    valid = set(REGRESSION_FIXTURE_KEYS)
    unknown = [item for item in wanted if item not in valid]
    if unknown:
        raise RuntimeError(f"unknown regression fixtures: {', '.join(unknown)}")
    out: list[str] = []
    for item in wanted:
        if item not in out:
            out.append(item)
    return out


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_json_tail(text: str) -> dict[str, Any]:
    tail = str(text or "").strip()
    start = tail.rfind("{")
    while start >= 0:
        try:
            return json.loads(tail[start:])
        except json.JSONDecodeError:
            start = tail.rfind("{", 0, start)
    raise RuntimeError("failed to parse trailing JSON payload")


def _probe_primary_fps(media: Path) -> float:
    try:
        info = dict(probe_media(str(media)) or {})
    except Exception:
        info = {}
    raw = info.get("fps", info.get("frame_rate", 30.0))
    try:
        value = float(raw or 30.0)
    except Exception:
        value = 30.0
    return value if value > 0 else 30.0


def _selected_source_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        source = str(
            row.get("stt_selected_source")
            or row.get("stt_source")
            or row.get("stt_preview_source")
            or ""
        ).strip()
        if source:
            counter[source] += 1
    return dict(sorted(counter.items()))


def _quality_label_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        label = str(
            row.get("stt_score_label")
            or row.get("subtitle_confidence_label")
            or row.get("subtitle_status_source")
            or ""
        ).strip()
        if label:
            counter[label] += 1
    return dict(sorted(counter.items()))


def _line_break_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    readability = dict(score_readability(rows, {}) or {})
    return {
        "readability_score": float(readability.get("readability_score", 0.0) or 0.0),
        "avg_lines_per_segment": float(readability.get("avg_lines_per_segment", 0.0) or 0.0),
        "avg_max_line_chars": float(readability.get("avg_max_line_chars", 0.0) or 0.0),
        "two_line_segments": int(readability.get("two_line_segments", 0) or 0),
        "over_two_line_segments": int(readability.get("over_two_line_segments", 0) or 0),
        "orphan_line_segments": int(readability.get("orphan_line_segments", 0) or 0),
        "packaging_changed_segments": int(readability.get("packaging_changed_segments", 0) or 0),
    }


def _copy_file_if_exists(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _project_roundtrip_summary(
    *,
    media: Path,
    rows: list[dict[str, Any]],
    output_dir: Path,
    project_name: str,
) -> dict[str, Any]:
    project_path = output_dir / f"{project_name}.aissproj"
    fps = _probe_primary_fps(media)
    project = {
        "project_name": project_name,
        "project_path": str(project_path),
        "timeline": {"timebase": {"primary_fps": fps}, "tracks": [{"clips": []}]},
        "editor_state": build_editor_state(
            mode="single",
            media_files=[str(media)],
            segments=[],
            primary_fps=fps,
        ),
    }
    final_segments = [dict(row) for row in rows]
    externalize_project_text_assets(
        str(project_path),
        project,
        final_segments=final_segments,
        stt_tracks={},
    )
    write_project_file(str(project_path), project)
    clear_project_file_cache(str(project_path))
    loaded = load_project(str(project_path), hydrate_text_assets=False) or {}
    roundtrip_rows = project_segments_to_editor(loaded, include_analysis_candidates=False)
    preserved_anchor_segments = 0
    for row in roundtrip_rows:
        if row.get("_stt_original_candidate_start") is not None and row.get("_stt_original_candidate_end") is not None:
            preserved_anchor_segments += 1
    return {
        "project_path": str(project_path),
        "reloaded_segment_count": len(roundtrip_rows),
        "selected_source_counts": _selected_source_counts(roundtrip_rows),
        "quality_label_counts": _quality_label_counts(roundtrip_rows),
        "line_breaks": _line_break_summary(roundtrip_rows),
        "preserved_anchor_segments": preserved_anchor_segments,
    }


def _segment_artifact_summary(
    *,
    media: Path,
    raw_rows: list[dict[str, Any]],
    output_rows: list[dict[str, Any]],
    output_dir: Path,
    project_name: str,
) -> dict[str, Any]:
    roundtrip = _project_roundtrip_summary(
        media=media,
        rows=output_rows,
        output_dir=output_dir,
        project_name=project_name,
    )
    return {
        "raw_segment_count": len(raw_rows),
        "final_segment_count": len(output_rows),
        "raw_selected_source_counts": _selected_source_counts(raw_rows),
        "final_selected_source_counts": _selected_source_counts(output_rows),
        "raw_quality_label_counts": _quality_label_counts(raw_rows),
        "final_quality_label_counts": _quality_label_counts(output_rows),
        "line_breaks": _line_break_summary(output_rows),
        "saved_project_state": roundtrip,
    }


def _fixture_summary_markdown(title: str, payload: dict[str, Any]) -> str:
    lines = [
        f"# {title}",
        "",
        f"- Media: `{payload.get('media')}`",
        f"- Artifact dir: `{payload.get('artifact_dir')}`",
        f"- Fixture kind: `{payload.get('fixture_kind')}`",
    ]
    metrics = dict(payload.get("metrics") or {})
    if metrics:
        lines.extend(
            [
                f"- Quality score: `{metrics.get('quality_score')}`",
                f"- Timing score: `{metrics.get('timing_score')}`",
                f"- Readability score: `{metrics.get('readability_score')}`",
                f"- Elapsed sec: `{metrics.get('elapsed_sec')}`",
            ]
        )
    segments = dict(payload.get("segments") or {})
    line_breaks = dict(segments.get("line_breaks") or {})
    saved_state = dict(segments.get("saved_project_state") or {})
    lines.extend(
        [
            f"- Raw segments: `{segments.get('raw_segment_count')}`",
            f"- Final segments: `{segments.get('final_segment_count')}`",
            f"- Final selected sources: `{segments.get('final_selected_source_counts')}`",
            f"- Final quality labels: `{segments.get('final_quality_label_counts')}`",
            f"- Two-line segments: `{line_breaks.get('two_line_segments')}`",
            f"- Over-two-line segments: `{line_breaks.get('over_two_line_segments')}`",
            f"- Orphan lines: `{line_breaks.get('orphan_line_segments')}`",
            f"- Saved project: `{saved_state.get('project_path')}`",
            f"- Reloaded segments: `{saved_state.get('reloaded_segment_count')}`",
            f"- Preserved anchors: `{saved_state.get('preserved_anchor_segments')}`",
        ]
    )
    return "\n".join(lines) + "\n"


def _run_mode_fixture(
    *,
    fixture_key: str,
    media: Path,
    reference_srt: Path,
    duration_sec: float,
    artifact_dir: Path,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(ROOT / "tools" / "benchmark_subtitle_pipeline_variants.py"),
        "--suite",
        "modes",
        "--media",
        str(media),
        "--reference-srt",
        str(reference_srt),
        "--duration-sec",
        str(duration_sec),
        "--keep-artifacts",
    ]
    proc = subprocess.run(
        command,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "runner_stdout.log").write_text(proc.stdout, encoding="utf-8")
    (artifact_dir / "runner_stderr.log").write_text(proc.stderr, encoding="utf-8")
    tail = _extract_json_tail(proc.stdout)
    benchmark_json = Path(str(tail.get("json") or "")).expanduser()
    benchmark_md = Path(str(tail.get("markdown") or "")).expanduser()
    payload = dict(_read_json(benchmark_json) or {})
    _copy_file_if_exists(benchmark_json, artifact_dir / "benchmark_results.json")
    _copy_file_if_exists(benchmark_md, artifact_dir / "benchmark_results.md")
    modes: list[dict[str, Any]] = []
    for row in list(payload.get("ranked_results") or []):
        variant_name = str(row.get("name") or "").strip()
        if not variant_name:
            continue
        src_dir = benchmark_json.parent / variant_name
        dst_dir = artifact_dir / variant_name
        _copy_file_if_exists(src_dir / "raw_segments.json", dst_dir / "raw_segments.json")
        _copy_file_if_exists(src_dir / "output_segments.json", dst_dir / "output_segments.json")
        raw_rows = list(_read_json(src_dir / "raw_segments.json") or [])
        output_rows = list(_read_json(src_dir / "output_segments.json") or [])
        mode_payload = {
            "name": variant_name,
            "metrics": {
                "quality_score": float(dict(row.get("quality") or {}).get("quality_score", 0.0) or 0.0),
                "timing_score": float(dict(row.get("quality") or {}).get("timing_score", 0.0) or 0.0),
                "readability_score": float(dict(row.get("readability") or {}).get("readability_score", 0.0) or 0.0),
                "elapsed_sec": float(row.get("elapsed_sec", 0.0) or 0.0),
                "rank": int(row.get("rank", 0) or 0),
            },
            "segments": _segment_artifact_summary(
                media=media,
                raw_rows=raw_rows,
                output_rows=output_rows,
                output_dir=dst_dir,
                project_name=f"{fixture_key}_{variant_name}",
            ),
        }
        _json_dump(dst_dir / "artifact_summary.json", mode_payload)
        (dst_dir / "artifact_summary.md").write_text(
            _fixture_summary_markdown(
                f"{fixture_key}:{variant_name}",
                {
                    "media": str(media),
                    "artifact_dir": str(dst_dir),
                    "fixture_kind": fixture_key,
                    **mode_payload,
                },
            ),
            encoding="utf-8",
        )
        modes.append(mode_payload)
    fixture_payload = {
        "fixture_kind": fixture_key,
        "media": str(media),
        "reference_srt": str(reference_srt),
        "artifact_dir": str(artifact_dir),
        "command": command,
        "benchmark_json": str(benchmark_json),
        "benchmark_markdown": str(benchmark_md),
        "modes": modes,
    }
    _json_dump(artifact_dir / "fixture_summary.json", fixture_payload)
    (artifact_dir / "fixture_summary.md").write_text(
        _fixture_summary_markdown(
            f"{fixture_key}:modes",
            {
                "media": str(media),
                "artifact_dir": str(artifact_dir),
                "fixture_kind": fixture_key,
                "metrics": {},
                "segments": {},
            },
        ),
        encoding="utf-8",
    )
    return fixture_payload


def _run_full_fixture(
    *,
    fixture_key: str,
    media: Path,
    mode: str,
    artifact_dir: Path,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    payload = run_full_verification(media, mode=mode, output_dir=artifact_dir)
    result = dict(payload.get("result") or {})
    variant_name = str(result.get("name") or f"full_{mode}")
    variant_dir = artifact_dir / variant_name
    raw_rows = list(_read_json(variant_dir / "raw_segments.json") or [])
    output_rows = list(_read_json(variant_dir / "output_segments.json") or [])
    fixture_payload = {
        "fixture_kind": fixture_key,
        "media": str(media),
        "artifact_dir": str(artifact_dir),
        "mode": mode,
        "metrics": {
            "quality_score": float(dict(result.get("quality") or {}).get("quality_score", 0.0) or 0.0),
            "timing_score": float(dict(result.get("quality") or {}).get("timing_score", 0.0) or 0.0),
            "readability_score": float(dict(result.get("readability") or {}).get("readability_score", 0.0) or 0.0),
            "elapsed_sec": float(result.get("elapsed_sec", 0.0) or 0.0),
            "completion_avg_quality": float(payload.get("completion_avg_quality", 0.0) or 0.0),
            "self_review_overall_score": float(payload.get("self_review_overall_score", 0.0) or 0.0),
        },
        "segments": _segment_artifact_summary(
            media=media,
            raw_rows=raw_rows,
            output_rows=output_rows,
            output_dir=variant_dir,
            project_name=f"{fixture_key}_{variant_name}",
        ),
        "full_verify_json": str(artifact_dir / "tinyping_full_verify.json"),
        "full_verify_markdown": str(artifact_dir / "tinyping_full_verify.md"),
        "full_verify_progress": str(artifact_dir / "tinyping_full_verify_progress.json"),
    }
    _json_dump(artifact_dir / "fixture_summary.json", fixture_payload)
    (artifact_dir / "fixture_summary.md").write_text(
        _fixture_summary_markdown(f"{fixture_key}:{mode}", fixture_payload),
        encoding="utf-8",
    )
    return fixture_payload


def _write_regression_pack_summary(pack_dir: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Subtitle Regression Pack",
        "",
        f"- Source run dir: `{payload.get('source_run_dir')}`",
        f"- Tiniping summary: `{payload.get('tiniping_summary_md')}`",
        "",
        "## Fixtures",
        "",
    ]
    fixtures = dict(payload.get("fixtures") or {})
    for key in REGRESSION_FIXTURE_KEYS:
        item = dict(fixtures.get(key) or {})
        if not item:
            continue
        lines.extend(
            [
                f"### {key}",
                "",
                f"- Artifact dir: `{item.get('artifact_dir')}`",
                f"- Media: `{item.get('media')}`",
            ]
        )
        if "modes" in item:
            for mode_item in item.get("modes") or []:
                metrics = dict(mode_item.get("metrics") or {})
                segments = dict(mode_item.get("segments") or {})
                lines.append(
                    f"- {mode_item.get('name')}: quality={metrics.get('quality_score')}, readability={metrics.get('readability_score')}, final_sources={segments.get('final_selected_source_counts')}"
                )
        else:
            metrics = dict(item.get("metrics") or {})
            segments = dict(item.get("segments") or {})
            lines.append(
                f"- mode={item.get('mode')}: quality={metrics.get('quality_score')}, readability={metrics.get('readability_score')}, final_sources={segments.get('final_selected_source_counts')}"
            )
        lines.append("")
    (pack_dir / "subtitle_regression_pack.md").write_text("\n".join(lines), encoding="utf-8")


def _build_regression_pack(
    *,
    source_run_dir: Path,
    tiniping_summary_md: Path,
    fixtures: list[str],
    pack_dir: Path,
    x5_duration_sec: float,
    full_verify_mode: str,
) -> dict[str, Any]:
    pack_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema": "ai_subtitle_studio.subtitle_regression_pack.v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_run_dir": str(source_run_dir),
        "tiniping_summary_md": str(tiniping_summary_md),
        "fixtures": {},
    }
    if "x5" in fixtures:
        payload["fixtures"]["x5"] = _run_mode_fixture(
            fixture_key="x5",
            media=DEFAULT_X5_MEDIA,
            reference_srt=DEFAULT_X5_REFERENCE,
            duration_sec=x5_duration_sec,
            artifact_dir=pack_dir / "x5_slice",
        )
    if "tinyping_short" in fixtures:
        payload["fixtures"]["tinyping_short"] = _run_mode_fixture(
            fixture_key="tinyping_short",
            media=DEFAULT_TINYPING_MEDIA,
            reference_srt=DEFAULT_TINYPING_REFERENCE,
            duration_sec=60.0,
            artifact_dir=pack_dir / "tinyping_first_minute",
        )
    if "macau" in fixtures:
        payload["fixtures"]["macau"] = _run_full_fixture(
            fixture_key="macau",
            media=DEFAULT_MACAU_MEDIA,
            mode=full_verify_mode,
            artifact_dir=pack_dir / "macau_smoke",
        )
    if "tinyping_full" in fixtures:
        payload["fixtures"]["tinyping_full"] = _run_full_fixture(
            fixture_key="tinyping_full",
            media=DEFAULT_TINYPING_MEDIA,
            mode=full_verify_mode,
            artifact_dir=pack_dir / "tinyping_full",
        )
    _json_dump(pack_dir / "subtitle_regression_pack.json", payload)
    _write_regression_pack_summary(pack_dir, payload)
    return payload
