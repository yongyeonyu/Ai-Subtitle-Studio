# Version: 03.10.03
# Phase: PHASE2
"""Apply subtitle split and Gap rules to STT preview candidate lanes."""
from __future__ import annotations

from logger import get_logger


def optimize_stt_preview_segments(
    segments: list[dict],
    *,
    source_label: str = "STT1",
    vad_segments: list[dict] | None = None,
    cut_boundaries: list[dict] | None = None,
    cut_boundary_enabled: bool = True,
    clip_offset: float = 0.0,
    clip_idx: int | None = None,
    clip_path: str | None = None,
) -> list[dict]:
    """Return STT candidate preview rows after the normal subtitle optimizer."""
    if not segments:
        return []

    label = str(source_label or "STT1").strip().upper() or "STT1"
    raw = [dict(seg) for seg in segments if isinstance(seg, dict)]
    if not raw:
        return []

    try:
        from core.engine.subtitle_engine import optimize_stt_candidate_segments

        optimized = optimize_stt_candidate_segments(raw, vad_segments=vad_segments or [])
        if optimized:
            get_logger().log(f"  ✅ [{label}] 후보 자막 분리/간격 규칙 적용 완료 ({len(raw)}개 → {len(optimized)}개)")
        else:
            get_logger().log(f"  ℹ️ [{label}] 후보 자막 분리/간격 규칙 적용 완료 ({len(raw)}개 → 0개)")
    except Exception as exc:
        get_logger().log(f"  ⚠️ [{label}] 후보 자막 분리/간격 규칙 적용 실패, 원본 후보 유지: {exc}")
        optimized = raw

    if cut_boundaries:
        try:
            from core.cut_boundary import split_segments_by_cut_boundaries

            optimized = split_segments_by_cut_boundaries(
                optimized,
                cut_boundaries,
                enabled=bool(cut_boundary_enabled),
            )
        except Exception as exc:
            get_logger().log(f"  ⚠️ [{label}] 컷 경계 후보 분할 실패, 기존 후보 유지: {exc}")

    offset = float(clip_offset or 0.0)
    preview: list[dict] = []
    for seg in optimized or []:
        try:
            start = float(seg.get("start", 0.0) or 0.0) + offset
            end = float(seg.get("end", start) or start) + offset
        except Exception:
            continue
        text = str(seg.get("text", "") or "").strip()
        if not text:
            continue
        row = dict(seg)
        row["start"] = start
        row["end"] = max(start + 0.05, end)
        row["text"] = text
        row["stt_preview_source"] = label
        row["stt_pending"] = True
        row["_live_stt_preview"] = True
        row["stt_preview_optimized"] = True
        row["stt_preview_optimizer"] = "subtitle_split_gap_rules"
        if clip_idx is not None:
            row["_clip_idx"] = clip_idx
        if clip_path:
            row["_clip_file"] = clip_path
        preview.append(row)
    return preview


__all__ = ["optimize_stt_preview_segments"]
