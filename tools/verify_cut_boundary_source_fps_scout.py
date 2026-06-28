#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
import subprocess
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.cut_boundary_auto_scan import precise_cut_boundary_timing, resolve_pioneer_pipe_fps, source_fps_parts
from core.frame_time import sec_to_frame
from core.native_json import dumps_json_bytes
from core.platform_compat import ffmpeg_binary, ffprobe_binary, hidden_subprocess_kwargs
from core.visual_cut_jump import build_visual_cut_sample, score_visual_cut_pair


def _parse_ratio(text: str) -> float:
    raw = str(text or "").strip()
    if "/" in raw:
        left, right = raw.split("/", 1)
        try:
            return float(left) / float(right)
        except Exception:
            return 0.0
    try:
        return float(raw)
    except Exception:
        return 0.0


def _probe_video(path: Path, *, timeout_sec: float = 120.0, fps_override: float = 0.0) -> dict[str, Any]:
    cmd = [
        ffprobe_binary(),
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,nb_frames,r_frame_rate,duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=max(1.0, float(timeout_sec or 120.0)),
            **hidden_subprocess_kwargs(strip_qt=True),
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "ffprobe failed")
    except (subprocess.TimeoutExpired, RuntimeError) as exc:
        if float(fps_override or 0.0) <= 0.0:
            raise
        return _spotlight_video_metadata(path, fps=float(fps_override or 0.0), probe_error=str(exc))
    payload = json.loads(proc.stdout or "{}")
    stream = (payload.get("streams") or [{}])[0] or {}
    fps = _parse_ratio(str(stream.get("r_frame_rate") or "0"))
    fps_num, fps_den = source_fps_parts(fps)
    return {
        "width": int(float(stream.get("width") or 0)),
        "height": int(float(stream.get("height") or 0)),
        "frame_count": int(float(stream.get("nb_frames") or 0)),
        "duration_sec": float(stream.get("duration") or 0.0),
        "fps": fps,
        "fps_num": fps_num,
        "fps_den": fps_den,
        "r_frame_rate": str(stream.get("r_frame_rate") or ""),
        "probe_source": "ffprobe",
    }


def _spotlight_video_metadata(path: Path, *, fps: float, probe_error: str = "") -> dict[str, Any]:
    width = 0
    height = 0
    duration = 0.0
    try:
        proc = subprocess.run(
            [
                "mdls",
                "-name",
                "kMDItemDurationSeconds",
                "-name",
                "kMDItemPixelWidth",
                "-name",
                "kMDItemPixelHeight",
                str(path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        text = proc.stdout or ""
        for line in text.splitlines():
            if "kMDItemDurationSeconds" in line:
                duration = float(line.split("=", 1)[1].strip())
            elif "kMDItemPixelWidth" in line:
                width = int(float(line.split("=", 1)[1].strip()))
            elif "kMDItemPixelHeight" in line:
                height = int(float(line.split("=", 1)[1].strip()))
    except Exception:
        pass
    fps_num, fps_den = source_fps_parts(fps)
    frame_count = int(round(duration * fps)) if duration > 0.0 and fps > 0.0 else 0
    return {
        "width": width,
        "height": height,
        "frame_count": frame_count,
        "duration_sec": duration,
        "fps": fps,
        "fps_num": fps_num,
        "fps_den": fps_den,
        "r_frame_rate": f"{fps_num}/{fps_den}" if fps_num and fps_den else "",
        "probe_source": "spotlight_fps_override",
        "probe_error": probe_error[:500],
    }


def _read_gray_frames(
    path: Path,
    frames: list[int],
    *,
    width: int,
    height: int,
    timeout_sec: float = 180.0,
) -> dict[int, Any]:
    import numpy as np

    ordered = sorted(set(int(frame) for frame in frames))
    if not ordered:
        return {}
    try:
        import cv2

        cap = cv2.VideoCapture(str(path))
        out: dict[int, Any] = {}
        try:
            if cap is not None and cap.isOpened():
                for frame_no in ordered:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_no))
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        continue
                    gray = cv2.cvtColor(
                        cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA),
                        cv2.COLOR_BGR2GRAY,
                    )
                    out[frame_no] = gray.copy()
        finally:
            try:
                cap.release()
            except Exception:
                pass
        if len(out) == len(ordered):
            return out
    except Exception:
        pass

    selector = "+".join(f"eq(n\\,{frame})" for frame in ordered)
    vf = f"select='{selector}',scale={width}:{height}:flags=fast_bilinear,format=gray"
    cmd = [
        ffmpeg_binary(),
        "-hide_banner",
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(path),
        "-vf",
        vf,
        "-vsync",
        "0",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "pipe:1",
    ]
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=max(30.0, float(timeout_sec or 180.0)),
        **hidden_subprocess_kwargs(strip_qt=True),
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="replace").strip() or "ffmpeg frame extraction failed")
    frame_size = int(width * height)
    out: dict[int, Any] = {}
    for index, frame_no in enumerate(ordered):
        start = index * frame_size
        end = start + frame_size
        chunk = proc.stdout[start:end]
        if len(chunk) != frame_size:
            continue
        out[frame_no] = np.frombuffer(chunk, dtype=np.uint8).reshape((height, width)).copy()
    return out


def _parse_pairs(text: str) -> list[tuple[int, int]]:
    pairs = []
    for chunk in str(text or "").split(","):
        item = chunk.strip()
        if not item:
            continue
        left, right = item.split(":", 1)
        pairs.append((int(left), int(right)))
    return pairs


def verify_source_fps_scout(
    media_path: Path,
    *,
    pairs: list[tuple[int, int]],
    width: int,
    height: int,
    output_dir: Path,
    pipe_max_fps: float = 60.0,
    probe_timeout_sec: float = 120.0,
    frame_extract_timeout_sec: float = 180.0,
    fps_override: float = 0.0,
    allow_metadata_only: bool = False,
) -> dict[str, Any]:
    import cv2

    started = time.time()
    info = _probe_video(media_path, timeout_sec=probe_timeout_sec, fps_override=fps_override)
    fps = float(info["fps"] or 0.0)
    settings = {
        "scan_cut_pioneer_pipe_source_fps_enabled": True,
        "scan_cut_pioneer_pipe_source_max_fps": float(pipe_max_fps or 60.0),
        "scan_cut_pioneer_pipe_score_threshold": 40.0,
        "scan_cut_pioneer_pipe_region_threshold": 18.0,
        "scan_cut_pioneer_pipe_regions_required": 2,
        "scan_cut_pioneer_pipe_pixel_ratio_threshold": 0.18,
        "scan_cut_pioneer_pipe_motion_threshold": 6.0,
    }
    pipe_fps = resolve_pioneer_pipe_fps(settings, source_fps=fps, fallback_fps=1.0)
    all_frames = [frame for pair in pairs for frame in pair]
    frame_map = {}
    frame_extract_error = ""
    if not allow_metadata_only:
        try:
            frame_map = _read_gray_frames(
                media_path,
                all_frames,
                width=width,
                height=height,
                timeout_sec=frame_extract_timeout_sec,
            )
        except Exception as exc:
            frame_extract_error = str(exc)[:500]
    rows = []
    for left_frame, right_frame in pairs:
        left = frame_map.get(left_frame)
        right = frame_map.get(right_frame)
        if left is None or right is None:
            timing = precise_cut_boundary_timing(right_frame / fps, 0.0, fps, sec_to_frame) if fps > 0.0 else {}
            frame_preserved = int(timing.get("timeline_frame") or -1) == int(right_frame)
            rows.append({
                "left_frame": left_frame,
                "right_frame": right_frame,
                "candidate_frame": int(timing.get("timeline_frame") or 0),
                "candidate_sec": float(timing.get("timeline_sec") or 0.0),
                "candidate_detected": False,
                "frame_preserved": bool(frame_preserved),
                "pair_passed": bool(allow_metadata_only and frame_preserved),
                "acceptance_basis": "metadata_frame_grid_preserved" if allow_metadata_only and frame_preserved else "missing",
                "reason": "metadata_only" if allow_metadata_only else "frame_extract_missing",
            })
            continue
        left_sample = build_visual_cut_sample(left, cv2, mode="fast4", width=width, settings=settings)
        right_sample = build_visual_cut_sample(right, cv2, mode="fast4", width=width, settings=settings)
        metrics = score_visual_cut_pair(left_sample, right_sample, cv2, settings=settings, region_threshold=18.0)
        score = float(metrics.get("score", 0.0) or 0.0)
        region_hits = int(metrics.get("region_hits", 0) or 0)
        pixel_ratio = float(metrics.get("pixel_ratio", 0.0) or 0.0)
        motion_jump = float(metrics.get("motion_jump", 0.0) or 0.0)
        detected = score >= 40.0 and region_hits >= 2 and (pixel_ratio >= 0.18 or motion_jump >= 6.0)
        timing = precise_cut_boundary_timing(right_frame / fps, 0.0, fps, sec_to_frame)
        frame_preserved = int(timing["timeline_frame"]) == int(right_frame)
        rows.append({
            "left_frame": left_frame,
            "right_frame": right_frame,
            "candidate_frame": int(timing["timeline_frame"]),
            "candidate_sec": float(timing["timeline_sec"]),
            "candidate_detected": bool(detected),
            "frame_preserved": frame_preserved,
            "pair_passed": bool(detected or frame_preserved),
            "acceptance_basis": "detected" if detected else "preserved" if frame_preserved else "missing",
            "score": round(score, 3),
            "region_hits": region_hits,
            "pixel_ratio": round(pixel_ratio, 6),
            "edge_ratio": round(float(metrics.get("edge_ratio", 0.0) or 0.0), 6),
            "motion_jump": round(motion_jump, 3),
            "flow_residual": round(float(metrics.get("flow_residual", 0.0) or 0.0), 3),
            "flow_mag": round(float(metrics.get("flow_mean", 0.0) or 0.0), 3),
            "flow_coherence": round(float(metrics.get("flow_coherence", 0.0) or 0.0), 6),
            "backend": str(metrics.get("backend", "") or ""),
            "metrics_backend": str(metrics.get("metrics_backend", "") or ""),
        })
    passed = all(bool(row.get("pair_passed")) for row in rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "ai_subtitle_studio.cut_boundary_source_fps_scout.v1",
        "media_path": str(media_path),
        "media": info,
        "settings": settings,
        "pipe_fps": pipe_fps,
        "pipe_fps_num": source_fps_parts(pipe_fps)[0],
        "pipe_fps_den": source_fps_parts(pipe_fps)[1],
        "scale": {"width": width, "height": height},
        "timeouts": {
            "probe_timeout_sec": max(1.0, float(probe_timeout_sec or 120.0)),
            "frame_extract_timeout_sec": max(30.0, float(frame_extract_timeout_sec or 180.0)),
        },
        "allow_metadata_only": bool(allow_metadata_only),
        "frame_extract_status": "metadata_only" if allow_metadata_only else "ok" if not frame_extract_error else "failed",
        "frame_extract_error": frame_extract_error,
        "pairs": rows,
        "passed": passed,
        "elapsed_sec": round(time.time() - started, 3),
    }
    out_path = output_dir / "source_fps_scout.json"
    out_path.write_bytes(dumps_json_bytes(manifest, indent=2, sort_keys=True, append_newline=True))
    manifest["artifact_path"] = str(out_path)
    _write_markdown_report(output_dir / "source_fps_scout.md", manifest)
    return manifest


def _write_markdown_report(path: Path, manifest: dict[str, Any]) -> None:
    pairs = manifest.get("pairs") if isinstance(manifest.get("pairs"), list) else []
    lines = [
        "# Cut Boundary Source-FPS Scout",
        "",
        f"- Passed: `{bool(manifest.get('passed'))}`",
        f"- Media: `{manifest.get('media_path')}`",
        f"- Pipe fps: `{manifest.get('pipe_fps')}` (`{manifest.get('pipe_fps_num')}/{manifest.get('pipe_fps_den')}`)",
        f"- Scale: `{(manifest.get('scale') or {}).get('width')}x{(manifest.get('scale') or {}).get('height')}`",
        f"- Probe source: `{(manifest.get('media') or {}).get('probe_source', '')}`",
        f"- Frame extract status: `{manifest.get('frame_extract_status')}`",
        f"- Metadata-only fallback: `{bool(manifest.get('allow_metadata_only'))}`",
        f"- Elapsed: `{manifest.get('elapsed_sec')}`",
        "",
        "| Left frame | Boundary frame | Candidate frame | Detected | Frame preserved | Passed | Basis | Score | Pixel ratio | Motion jump |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in pairs:
        if not isinstance(row, dict):
            continue
        lines.append(
            "| {left} | {right} | {candidate} | {detected} | {preserved} | {passed} | {basis} | {score} | {pixel} | {motion} |".format(
                left=row.get("left_frame"),
                right=row.get("right_frame"),
                candidate=row.get("candidate_frame", ""),
                detected=bool(row.get("candidate_detected")),
                preserved=bool(row.get("frame_preserved")),
                passed=bool(row.get("pair_passed")),
                basis=row.get("acceptance_basis", ""),
                score=row.get("score", ""),
                pixel=row.get("pixel_ratio", ""),
                motion=row.get("motion_jump", ""),
            )
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify source-fps low-res cut-boundary scout on exact target frames.")
    parser.add_argument("media", type=Path)
    parser.add_argument("--pairs", default="2765:2766,2676:2677")
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=180)
    parser.add_argument("--pipe-max-fps", type=float, default=60.0)
    parser.add_argument("--fps-override", default="")
    parser.add_argument("--allow-metadata-only", action="store_true")
    parser.add_argument("--probe-timeout-sec", type=float, default=120.0)
    parser.add_argument("--frame-extract-timeout-sec", type=float, default=180.0)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = verify_source_fps_scout(
        args.media,
        pairs=_parse_pairs(args.pairs),
        width=max(64, min(960, int(args.width or 320))),
        height=max(36, min(540, int(args.height or 180))),
        output_dir=args.output_dir,
        pipe_max_fps=float(args.pipe_max_fps or 60.0),
        probe_timeout_sec=float(args.probe_timeout_sec or 120.0),
        frame_extract_timeout_sec=float(args.frame_extract_timeout_sec or 180.0),
        fps_override=_parse_ratio(args.fps_override),
        allow_metadata_only=bool(args.allow_metadata_only),
    )
    print(dumps_json_bytes(manifest, indent=2, sort_keys=True).decode("utf-8"))
    return 0 if manifest.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
