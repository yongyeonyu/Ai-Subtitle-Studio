#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.audio.media_processor import VideoProcessor  # noqa: E402
from core.performance import hardware_profile  # noqa: E402
from tools.benchmark_subtitle_pipeline_variants import (  # noqa: E402
    AudioProfile,
    Variant,
    _base_benchmark_settings,
    _bind_processor_settings,
    _copy_chunk_dir,
    _run_variant,
    benchmark_audio_profiles,
    benchmark_mode_lora_deep_profiles,
    benchmark_mode_lora_packaging_profiles,
    benchmark_mode_lora_selective_profiles,
    benchmark_mode_profiles,
    benchmark_variants,
    clip_reference,
    parse_srt,
)


DEFAULT_MEDIA = Path("/Users/u_mo_c/Downloads/티니핑/티니핑_유스어드벤처.MP4")
DEFAULT_REFERENCE = Path("/Users/u_mo_c/Downloads/티니핑/티니핑_유스어드벤처_완성.srt")


@dataclass(frozen=True)
class TimingIdea:
    name: str
    description: str
    variant: Variant
    audio_profile: AudioProfile | None = None
    use_baseline_raw_cache: bool = False


def _log(message: str) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"[tiniping-timing {stamp}] {message}", flush=True)


def _json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _compact_result(row: dict[str, Any]) -> dict[str, Any]:
    quality = dict(row.get("quality") or {})
    return {
        "name": row.get("name"),
        "phase": row.get("phase"),
        "description": row.get("description"),
        "elapsed_sec": float(row.get("elapsed_sec", 0.0) or 0.0),
        "raw_segments": int(row.get("raw_segments", 0) or 0),
        "final_segments": int(row.get("final_segments", 0) or 0),
        "quality_score": float(quality.get("quality_score", 0.0) or 0.0),
        "text_score": float(quality.get("text_score", 0.0) or 0.0),
        "timing_mae_sec": float(quality.get("timing_mae_sec", 0.0) or 0.0),
        "timing_score": float(quality.get("timing_score", 0.0) or 0.0),
        "overlap_score": float(quality.get("overlap_score", 0.0) or 0.0),
        "local_text_score": float(quality.get("local_text_score", 0.0) or 0.0),
        "count_score": float(quality.get("count_score", 0.0) or 0.0),
        "segment_count_delta": int(quality.get("segment_count_delta", 0) or 0),
        "error": str(row.get("error") or ""),
    }


def _timing_focus_score(row: dict[str, Any], baseline: dict[str, Any] | None = None) -> float:
    quality = dict(row.get("quality") or {})
    timing_score = float(quality.get("timing_score", 0.0) or 0.0)
    overlap_score = float(quality.get("overlap_score", 0.0) or 0.0)
    local_text_score = float(quality.get("local_text_score", 0.0) or 0.0)
    text_score = float(quality.get("text_score", 0.0) or 0.0)
    count_score = float(quality.get("count_score", 0.0) or 0.0)
    segment_count_delta = abs(int(quality.get("segment_count_delta", 0) or 0))
    score = (
        timing_score * 0.45
        + overlap_score * 0.20
        + local_text_score * 0.15
        + text_score * 0.10
        + count_score * 0.10
        - segment_count_delta * 0.20
    )
    if baseline:
        base_quality = dict(baseline.get("quality") or {})
        base_text = float(base_quality.get("text_score", 0.0) or 0.0)
        base_local = float(base_quality.get("local_text_score", 0.0) or 0.0)
        if text_score < base_text - 6.0:
            score -= (base_text - 6.0 - text_score) * 1.5
        if local_text_score < base_local - 8.0:
            score -= (base_local - 8.0 - local_text_score) * 1.5
    return round(score, 4)


def _eligible_for_top(row: dict[str, Any], baseline: dict[str, Any]) -> bool:
    if str(row.get("error") or "").strip():
        return False
    quality = dict(row.get("quality") or {})
    base_quality = dict(baseline.get("quality") or {})
    return (
        float(quality.get("text_score", 0.0) or 0.0) >= float(base_quality.get("text_score", 0.0) or 0.0) - 6.0
        and float(quality.get("local_text_score", 0.0) or 0.0) >= float(base_quality.get("local_text_score", 0.0) or 0.0) - 8.0
        and abs(int(quality.get("segment_count_delta", 0) or 0)) <= abs(int(base_quality.get("segment_count_delta", 0) or 0)) + 8
    )


def _rank_rows(rows: list[dict[str, Any]], baseline: dict[str, Any]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        quality = dict(item.get("quality") or {})
        item["timing_focus_score"] = _timing_focus_score(item, baseline)
        item["eligible_for_top"] = _eligible_for_top(item, baseline)
        item["timing_mae_sec"] = float(quality.get("timing_mae_sec", 0.0) or 0.0)
        item["local_text_score"] = float(quality.get("local_text_score", 0.0) or 0.0)
        item["text_score"] = float(quality.get("text_score", 0.0) or 0.0)
        item["count_delta_abs"] = abs(int(quality.get("segment_count_delta", 0) or 0))
        ranked.append(item)
    ranked.sort(
        key=lambda row: (
            1 if row.get("eligible_for_top") else 0,
            float(row.get("timing_focus_score", 0.0) or 0.0),
            -float(row.get("timing_mae_sec", 0.0) or 0.0),
            -float(row.get("local_text_score", 0.0) or 0.0),
            -float(row.get("text_score", 0.0) or 0.0),
            -float(dict(row.get("quality") or {}).get("quality_score", 0.0) or 0.0),
        ),
        reverse=True,
    )
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
    return ranked


def _extract_chunk(
    *,
    media: Path,
    settings: dict[str, Any],
    start_sec: float,
    end_sec: float,
    work_dir: Path,
    name: str,
) -> Path:
    processor = VideoProcessor()
    _bind_processor_settings(processor, settings)
    try:
        chunk_dir_text, _ = processor.extract_audio(
            str(media),
            target_start_sec=float(start_sec),
            target_end_sec=float(end_sec),
            is_single_segment=False,
        )
    finally:
        processor.release_runtime_models()
    chunk_source = Path(chunk_dir_text)
    if not chunk_source.exists():
        raise FileNotFoundError(chunk_source)
    return _copy_chunk_dir(chunk_source, work_dir / "_seed_chunks" / name)


def _variant_lookup(base_settings: dict[str, Any]) -> dict[str, Variant]:
    variants: dict[str, Variant] = {}
    for suite in (
        benchmark_variants(base_settings),
        benchmark_mode_profiles(base_settings),
        benchmark_mode_lora_deep_profiles(base_settings),
        benchmark_mode_lora_selective_profiles(base_settings),
        benchmark_mode_lora_packaging_profiles(base_settings),
    ):
        for variant in suite:
            variants.setdefault(variant.name, variant)
    return variants


def _audio_profile_lookup(base_settings: dict[str, Any]) -> dict[str, AudioProfile]:
    return {profile.name: profile for profile in benchmark_audio_profiles(base_settings)}


def build_timing_ideas(base_settings: dict[str, Any]) -> list[TimingIdea]:
    variants = _variant_lookup(base_settings)
    audio_profiles = _audio_profile_lookup(base_settings)

    ideas: list[TimingIdea] = [
        TimingIdea("mode_auto", "현재 Auto 기본 경로를 기준선으로 사용합니다.", variants["mode_auto"]),
        TimingIdea("mode_auto_piecewise_drift", "연속 구간 단위 piecewise drift timing 보정을 적용합니다.", variants["mode_auto_piecewise_drift"]),
        TimingIdea("mode_auto_adaptive_split", "route disagreement 기반 selective adaptive split v2를 적용합니다.", variants["mode_auto_adaptive_split"]),
        TimingIdea("mode_auto_adaptive_split_drift", "adaptive split v2와 piecewise drift를 함께 적용합니다.", variants["mode_auto_adaptive_split_drift"]),
        TimingIdea("mode_auto_deep_off", "Deep timing/output selector를 꺼서 타이밍 원형을 확인합니다.", variants["mode_auto_deep_off"]),
        TimingIdea("mode_auto_lora_off", "LoRA micro-merge를 꺼서 합치기/늘리기 영향을 뺍니다.", variants["mode_auto_lora_off"]),
        TimingIdea("mode_auto_lora_deep_off", "LoRA와 Deep을 모두 꺼서 STT 기반 timing 원형을 봅니다.", variants["mode_auto_lora_deep_off"]),
        TimingIdea("mode_auto_lora_full", "LoRA micro-merge를 전체 세그먼트에 강하게 적용합니다.", variants["mode_auto_lora_full"]),
        TimingIdea("mode_auto_lora_selective", "LoRA micro-merge를 가독성 낮은 구간에만 제한 적용합니다.", variants["mode_auto_lora_selective"]),
        TimingIdea("mode_auto_packaging_full", "LoRA merge는 끄고 포장만 전체 적용해 timing 흔들림을 줄여봅니다.", variants["mode_auto_packaging_full"]),
        TimingIdea("mode_auto_packaging_selective", "LoRA merge는 끄고 포장만 선택 적용합니다.", variants["mode_auto_packaging_selective"]),
        TimingIdea("split_lora_strong_cached", "짧은 자막을 더 적극적으로 병합해 과분절을 줄입니다.", variants["split_lora_strong_cached"], use_baseline_raw_cache=True),
        TimingIdea("split_deep_first_lora_off_cached", "Deep 판단만 먼저 두고 LoRA merge를 제거합니다.", variants["split_deep_first_lora_off_cached"], use_baseline_raw_cache=True),
        TimingIdea("split_netflix_style_cached", "긴 무음 중심의 보수적 병합 규칙을 적용합니다.", variants["split_netflix_style_cached"], use_baseline_raw_cache=True),
        TimingIdea("timing_vad_only_edge004_cached", "VAD post-align만 적용해 컷 경계 영향 없이 edge pad만 확인합니다.", variants["timing_vad_only_edge004_cached"], use_baseline_raw_cache=True),
        TimingIdea("timing_cut_only_edge008_cached", "컷 경계 guard만 적용해 VAD 없이 컷 경계 영향만 봅니다.", variants["timing_cut_only_edge008_cached"], use_baseline_raw_cache=True),
        TimingIdea("timing_cut_vad_edge004_cached", "컷 경계 + VAD + edge 0.04초 조합입니다.", variants["timing_cut_vad_edge004_cached"], use_baseline_raw_cache=True),
        TimingIdea("timing_cut_vad_edge008_cached", "컷 경계 + VAD + edge 0.08초 조합입니다.", variants["timing_cut_vad_edge008_cached"], use_baseline_raw_cache=True),
        TimingIdea("timing_cut_vad_edge012_cached", "컷 경계 + VAD + edge 0.12초 조합입니다.", variants["timing_cut_vad_edge012_cached"], use_baseline_raw_cache=True),
        TimingIdea("timing_cut_provisional_vad_edge008_cached", "임시 컷까지 포함해 VAD와 같이 경계를 강하게 묶습니다.", variants["timing_cut_provisional_vad_edge008_cached"], use_baseline_raw_cache=True),
        TimingIdea("word_ts_off_stt1", "단어 타임태그를 완전히 끄고 STT1 timing 원형을 확인합니다.", variants["word_ts_off_stt1"]),
        TimingIdea("word_ts_low_score_stt1", "저신뢰 구간만 단어 타임태그 정밀 패스를 적용합니다.", variants["word_ts_low_score_stt1"]),
        TimingIdea("word_ts_vad_boundary_stt1", "VAD 경계 위험 구간만 단어 타임태그 정밀 패스를 적용합니다.", variants["word_ts_vad_boundary_stt1"]),
        TimingIdea("word_ts_all_stt1", "전체 STT1에 단어 타임태그를 적용해 timing 상한을 확인합니다.", variants["word_ts_all_stt1"]),
        TimingIdea("phase2_serial_lora_deep_gate_then_stt2", "LoRA/Deep 진단 후 저신뢰 구간만 STT2와 단어 패스로 보강합니다.", variants["phase2_serial_lora_deep_gate_then_stt2"]),
        TimingIdea("stt_original_parallel_full_no_llm", "STT1/STT2를 병렬 전체 앙상블해서 시간축 후보를 넓게 가져갑니다.", variants["stt_original_parallel_full_no_llm"]),
        TimingIdea(
            "audio_ffmpeg_ten_vad_balanced",
            "오디오 필터를 FFmpeg+TEN VAD 균형형으로 바꿔 boundary 안정성을 확인합니다.",
            Variant(
                name="audio_ffmpeg_ten_vad_balanced",
                phase="audio_timing",
                description="Auto baseline + FFmpeg/TEN VAD balanced",
                method="selective_ensemble",
                overrides={},
                run_llm=False,
            ),
            audio_profile=audio_profiles["ffmpeg_ten_vad_balanced"],
        ),
        TimingIdea(
            "audio_ffmpeg_silero_relaxed",
            "FFmpeg+Silero relaxed로 짧은 발화 경계 복구를 노립니다.",
            Variant(
                name="audio_ffmpeg_silero_relaxed",
                phase="audio_timing",
                description="Auto baseline + FFmpeg/Silero relaxed",
                method="selective_ensemble",
                overrides={},
                run_llm=False,
            ),
            audio_profile=audio_profiles["ffmpeg_silero_relaxed"],
        ),
        TimingIdea(
            "audio_deepfilter_silero_quality",
            "DeepFilter+Silero 품질형으로 경계 보존과 잡음 억제를 함께 노립니다.",
            Variant(
                name="audio_deepfilter_silero_quality",
                phase="audio_timing",
                description="Auto baseline + DeepFilter/Silero quality",
                method="selective_ensemble",
                overrides={},
                run_llm=False,
            ),
            audio_profile=audio_profiles["deepfilter_silero_quality"],
        ),
        TimingIdea(
            "anchor_tight_cached",
            "anchor 허용 범위를 더 조여 start/end가 STT 경계에서 멀어지지 않게 합니다.",
            Variant(
                name="anchor_tight_cached",
                phase="anchor_timing",
                description="Tight anchor window + confirmed cut + VAD",
                method="cached_raw",
                run_llm=False,
                overrides={
                    "subtitle_timing_anchor_max_start_lag_sec": 0.04,
                    "subtitle_timing_anchor_max_end_lead_sec": 0.04,
                    "subtitle_timing_anchor_max_end_lag_sec": 0.08,
                    "vad_post_stt_align_enabled": True,
                    "vad_post_stt_edge_pad_sec": 0.04,
                    "subtitle_cut_boundary_guard_enabled": True,
                    "subtitle_bundle_use_confirmed_cuts": True,
                    "subtitle_bundle_use_provisional_cuts": False,
                },
            ),
            use_baseline_raw_cache=True,
        ),
        TimingIdea(
            "anchor_relaxed_cached",
            "anchor 허용 범위를 조금 넓혀 지나친 조임으로 인한 절단을 완화합니다.",
            Variant(
                name="anchor_relaxed_cached",
                phase="anchor_timing",
                description="Relaxed anchor window + confirmed cut + VAD",
                method="cached_raw",
                run_llm=False,
                overrides={
                    "subtitle_timing_anchor_max_start_lag_sec": 0.12,
                    "subtitle_timing_anchor_max_end_lead_sec": 0.10,
                    "subtitle_timing_anchor_max_end_lag_sec": 0.18,
                    "vad_post_stt_align_enabled": True,
                    "vad_post_stt_edge_pad_sec": 0.04,
                    "subtitle_cut_boundary_guard_enabled": True,
                    "subtitle_bundle_use_confirmed_cuts": True,
                    "subtitle_bundle_use_provisional_cuts": False,
                },
            ),
            use_baseline_raw_cache=True,
        ),
        TimingIdea(
            "anchor_tight_provisional_cached",
            "anchor를 조이고 임시 컷까지 허용해 긴 구간 드리프트를 더 일찍 잘라봅니다.",
            Variant(
                name="anchor_tight_provisional_cached",
                phase="anchor_timing",
                description="Tight anchor window + provisional cut + VAD",
                method="cached_raw",
                run_llm=False,
                overrides={
                    "subtitle_timing_anchor_max_start_lag_sec": 0.04,
                    "subtitle_timing_anchor_max_end_lead_sec": 0.04,
                    "subtitle_timing_anchor_max_end_lag_sec": 0.08,
                    "vad_post_stt_align_enabled": True,
                    "vad_post_stt_edge_pad_sec": 0.04,
                    "subtitle_cut_boundary_guard_enabled": True,
                    "subtitle_bundle_use_confirmed_cuts": True,
                    "subtitle_bundle_use_provisional_cuts": True,
                },
            ),
            use_baseline_raw_cache=True,
        ),
        TimingIdea(
            "word_ts_low_score_tight_shift_stt1",
            "저신뢰 구간만 단어 타임태그를 쓰되 허용 shift를 줄여 timing 튐을 막습니다.",
            Variant(
                name="word_ts_low_score_tight_shift_stt1",
                phase="word_timestamp",
                description="Selective word timestamp precision with tighter max timing shift",
                method="stt1_word_precision",
                run_llm=False,
                overrides={
                    "stt_ensemble_enabled": False,
                    "stt_selective_secondary_recheck_enabled": False,
                    "stt_word_timestamps_mode": "selective",
                    "stt_word_timestamps_default_enabled": False,
                    "stt_word_timestamps_precision_enabled": True,
                    "stt_word_timestamps_precision_threshold": 72.0,
                    "stt_word_timestamps_precision_max_segments": 32,
                    "stt_word_timestamps_precision_max_audio_sec": 100.0,
                    "stt_word_timestamps_precision_max_timing_shift_sec": 0.18,
                },
            ),
        ),
    ]
    return ideas


def _prepare_variant(base_settings: dict[str, Any], idea: TimingIdea, *, cached_raw_path: Path | None) -> Variant:
    overrides = dict(base_settings)
    overrides.update(idea.variant.overrides)
    if idea.audio_profile is not None:
        overrides.update(dict(idea.audio_profile.overrides or {}))
    if idea.use_baseline_raw_cache and cached_raw_path is not None:
        overrides["_benchmark_cached_raw_segments_path"] = str(cached_raw_path)
    return Variant(
        name=idea.variant.name,
        phase=idea.variant.phase,
        description=idea.variant.description,
        method=idea.variant.method,
        overrides=overrides,
        run_llm=idea.variant.run_llm,
    )


def _run_span(
    *,
    media: Path,
    reference_srt: Path,
    start_sec: float,
    duration_sec: float,
    ideas: list[TimingIdea],
    run_dir: Path,
    top_n: int,
) -> dict[str, Any]:
    end_sec = start_sec + duration_sec
    base_settings = _base_benchmark_settings("current")
    mode_variants = {variant.name: variant for variant in benchmark_mode_profiles(base_settings)}
    baseline_variant = mode_variants["mode_auto"]
    baseline_settings = dict(baseline_variant.overrides)
    baseline_settings["_benchmark_span_sec"] = duration_sec
    baseline_settings["selected_model"] = "사용 안함 (benchmark no-llm)"

    reference = clip_reference(parse_srt(reference_srt), start_sec, end_sec)
    span_dir = run_dir / f"{int(round(duration_sec))}s"
    span_dir.mkdir(parents=True, exist_ok=True)

    _log(f"{duration_sec:.0f}초 구간 기준선 chunk 추출 시작")
    baseline_chunk = _extract_chunk(
        media=media,
        settings=baseline_settings,
        start_sec=start_sec,
        end_sec=end_sec,
        work_dir=span_dir,
        name="baseline_auto",
    )
    _log("기준선 Auto 아이디어 실행")
    baseline_row = _run_variant(
        baseline_variant,
        chunk_source=baseline_chunk,
        work_dir=span_dir,
        base_settings=baseline_settings,
        reference=reference,
    )
    baseline_raw_path = span_dir / baseline_variant.name / "raw_segments.json"

    rows: list[dict[str, Any]] = [baseline_row]
    for idea in ideas:
        if idea.name == baseline_variant.name:
            continue
        idea_settings = dict(baseline_settings)
        if idea.audio_profile is not None:
            idea_settings.update(dict(idea.audio_profile.overrides or {}))
        idea_settings["_benchmark_span_sec"] = duration_sec
        chunk_source = baseline_chunk
        if idea.audio_profile is not None:
            _log(f"{idea.name} 오디오/VAD 재추출")
            chunk_source = _extract_chunk(
                media=media,
                settings=idea_settings,
                start_sec=start_sec,
                end_sec=end_sec,
                work_dir=span_dir,
                name=idea.name,
            )
        variant = _prepare_variant(idea_settings, idea, cached_raw_path=baseline_raw_path)
        _log(f"{idea.name} 실행")
        row = _run_variant(
            variant,
            chunk_source=chunk_source,
            work_dir=span_dir,
            base_settings=idea_settings,
            reference=reference,
        )
        rows.append(row)

    ranked = _rank_rows(rows, baseline_row)
    selected = [row for row in ranked if row.get("eligible_for_top")][:top_n]
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "media": str(media),
        "reference_srt": str(reference_srt),
        "start_sec": start_sec,
        "duration_sec": duration_sec,
        "end_sec": end_sec,
        "hardware": hardware_profile(),
        "baseline": _compact_result(baseline_row),
        "ranked": [
            {
                **_compact_result(row),
                "timing_focus_score": row.get("timing_focus_score"),
                "eligible_for_top": row.get("eligible_for_top"),
                "rank": row.get("rank"),
            }
            for row in ranked
        ],
        "selected_top": [
            {
                **_compact_result(row),
                "timing_focus_score": row.get("timing_focus_score"),
                "rank": row.get("rank"),
            }
            for row in selected
        ],
    }
    _json_dump(span_dir / "timing_ideas_results.json", payload)
    return {
        "payload": payload,
        "ranked": ranked,
        "selected": selected,
    }


def _write_summary(path: Path, short_payload: dict[str, Any], long_payload: dict[str, Any]) -> None:
    short_rows = list(short_payload.get("selected_top") or [])
    long_rows = list(long_payload.get("selected_top") or [])
    lines = [
        "# Tiniping Timing Ideas Benchmark",
        "",
        f"- Media: `{short_payload.get('media')}`",
        f"- Reference: `{short_payload.get('reference_srt')}`",
        f"- Short span: `{short_payload.get('duration_sec')}` sec",
        f"- Long span: `{long_payload.get('duration_sec')}` sec",
        "",
        "## Short Top",
        "",
        "| Rank | Idea | Timing MAE | Timing | Local | Text | Delta | Quality |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in short_rows:
        lines.append(
            "| {rank} | `{name}` | {mae:.4f} | {timing:.3f} | {local:.3f} | {text:.3f} | {delta} | {quality:.3f} |".format(
                rank=row.get("rank", ""),
                name=row.get("name", ""),
                mae=float(row.get("timing_mae_sec", 0.0) or 0.0),
                timing=float(row.get("timing_score", 0.0) or 0.0),
                local=float(row.get("local_text_score", 0.0) or 0.0),
                text=float(row.get("text_score", 0.0) or 0.0),
                delta=int(row.get("segment_count_delta", 0) or 0),
                quality=float(row.get("quality_score", 0.0) or 0.0),
            )
        )
    lines.extend(
        [
            "",
            "## Long Top",
            "",
            "| Rank | Idea | Timing MAE | Timing | Local | Text | Delta | Quality |",
            "|---:|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in long_rows:
        lines.append(
            "| {rank} | `{name}` | {mae:.4f} | {timing:.3f} | {local:.3f} | {text:.3f} | {delta} | {quality:.3f} |".format(
                rank=row.get("rank", ""),
                name=row.get("name", ""),
                mae=float(row.get("timing_mae_sec", 0.0) or 0.0),
                timing=float(row.get("timing_score", 0.0) or 0.0),
                local=float(row.get("local_text_score", 0.0) or 0.0),
                text=float(row.get("text_score", 0.0) or 0.0),
                delta=int(row.get("segment_count_delta", 0) or 0),
                quality=float(row.get("quality_score", 0.0) or 0.0),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark timing-improvement ideas on Tiniping.")
    parser.add_argument("--media", default=str(DEFAULT_MEDIA))
    parser.add_argument("--reference-srt", default=str(DEFAULT_REFERENCE))
    parser.add_argument("--start-sec", type=float, default=0.0)
    parser.add_argument("--short-sec", type=float, default=180.0)
    parser.add_argument("--long-sec", type=float, default=660.0)
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--ideas", nargs="*", default=[])
    args = parser.parse_args()

    media = Path(args.media).expanduser()
    reference_srt = Path(args.reference_srt).expanduser()
    if not media.exists():
        raise FileNotFoundError(media)
    if not reference_srt.exists():
        raise FileNotFoundError(reference_srt)

    base_settings = _base_benchmark_settings("current")
    ideas = build_timing_ideas(base_settings)
    if args.ideas:
        requested = {str(name).strip() for name in args.ideas if str(name).strip()}
        ideas = [idea for idea in ideas if idea.name in requested]
    created = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = ROOT / ".codex_work" / "benchmarks" / "tiniping_timing_ideas" / created
    run_dir.mkdir(parents=True, exist_ok=True)

    _log(f"3분 아이디어 {len(ideas)}개 실행 시작")
    short_result = _run_span(
        media=media,
        reference_srt=reference_srt,
        start_sec=float(args.start_sec),
        duration_sec=float(args.short_sec),
        ideas=ideas,
        run_dir=run_dir,
        top_n=max(1, int(args.top_n)),
    )
    top_names = [str(row.get("name") or "").strip() for row in short_result["selected"] if str(row.get("name") or "").strip()]
    top_set = set(top_names)
    top_ideas = [idea for idea in ideas if idea.name in top_set]
    _log(f"11분 재검증 대상: {', '.join(top_names) if top_names else '없음'}")
    long_result = _run_span(
        media=media,
        reference_srt=reference_srt,
        start_sec=float(args.start_sec),
        duration_sec=float(args.long_sec),
        ideas=top_ideas,
        run_dir=run_dir,
        top_n=max(1, int(args.top_n)),
    )

    summary_path = ROOT / "output" / "manual_verification" / "latest" / "tiniping_timing_ideas_summary.md"
    _write_summary(summary_path, short_result["payload"], long_result["payload"])
    _json_dump(
        run_dir / "final_summary.json",
        {
            "run_dir": str(run_dir),
            "summary_markdown": str(summary_path),
            "short_results": short_result["payload"],
            "long_results": long_result["payload"],
        },
    )
    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "summary_markdown": str(summary_path),
                "short_top": [row.get("name") for row in short_result["payload"].get("selected_top", [])],
                "long_top": [row.get("name") for row in long_result["payload"].get("selected_top", [])],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
