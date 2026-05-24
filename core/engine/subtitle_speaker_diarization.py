from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

SUBTITLE_SPEAKER_DIARIZATION_SCHEMA = "ai_subtitle_studio.subtitle_speaker_diarization.v1"


def normalize_runtime_speaker_id(value: Any) -> str:
    speaker = str(value or "").strip()
    if speaker.startswith("SPEAKER_"):
        speaker = speaker.replace("SPEAKER_", "", 1)
    return speaker or "00"


def dialogue_turn_speaker_pair(settings: dict[str, Any] | None = None) -> tuple[str, str]:
    settings = dict(settings or {})
    first = normalize_runtime_speaker_id(settings.get("spk1_id", "00"))
    second = normalize_runtime_speaker_id(settings.get("spk2_id", "01"))
    if second == first:
        second = "01" if first != "01" else "02"
    return first, second


def inline_dialogue_turns(text: Any, *, allow_missing_leading_marker: bool = False) -> list[str]:
    compact = re.sub(r"\s+", " ", str(text or "").replace("\n", " ")).strip()
    if not compact.startswith("-"):
        if not allow_missing_leading_marker or not re.search(r"\s-\s*\S", compact):
            return []
        compact = f"- {compact}"
    turns = [
        match.group(1).strip()
        for match in re.finditer(r"(?:^|\s)-\s*([^-]+?)(?=\s+-\s*\S|$)", compact)
        if match.group(1).strip()
    ]
    if len(turns) != 2:
        turns = [part.lstrip("-").strip() for part in re.split(r"\s+-\s*", compact) if part.strip()]
    turns = [turn for turn in turns if turn]
    if len(turns) != 2:
        return []
    return turns


def _speaker_map_rows(speaker_map: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None) -> list[dict[str, Any]]:
    return [dict(row) for row in list(speaker_map or []) if isinstance(row, dict)]


def speaker_sequence_for_range(
    start_t: float,
    end_t: float,
    speaker_map: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
) -> list[str]:
    start_sec = float(start_t or 0.0)
    end_sec = max(start_sec, float(end_t or start_sec))
    sequence: list[str] = []
    for item in sorted(
        _speaker_map_rows(speaker_map),
        key=lambda row: (float(row.get("start", 0.0) or 0.0), float(row.get("end", 0.0) or 0.0)),
    ):
        try:
            seg_start = float(item.get("start", 0.0) or 0.0)
            seg_end = float(item.get("end", seg_start) or seg_start)
        except Exception:
            continue
        if min(end_sec, seg_end) <= max(start_sec, seg_start):
            continue
        speaker = normalize_runtime_speaker_id(item.get("speaker"))
        if not sequence or sequence[-1] != speaker:
            sequence.append(speaker)
    return sequence


def speaker_for_segment(
    start_t: float,
    end_t: float,
    speaker_map: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> str:
    rows = _speaker_map_rows(speaker_map)
    if not rows:
        return "SPEAKER_00"
    start_sec = float(start_t or 0.0)
    end_sec = max(start_sec, float(end_t or start_sec))
    mid_time = (start_sec + end_sec) / 2.0

    overlap_durations: dict[str, float] = {}
    for spk_seg in rows:
        try:
            seg_start = float(spk_seg.get("start", 0.0) or 0.0)
            seg_end = float(spk_seg.get("end", seg_start) or seg_start)
        except Exception:
            continue
        overlap_start = max(start_sec, seg_start)
        overlap_end = min(end_sec, seg_end)
        if overlap_start < overlap_end:
            speaker = str(spk_seg.get("speaker") or "SPEAKER_00")
            overlap_durations[speaker] = overlap_durations.get(speaker, 0.0) + (overlap_end - overlap_start)

    if overlap_durations:
        return max(overlap_durations.items(), key=lambda item: item[1])[0]

    closest_spk = "SPEAKER_00"
    min_dist = float("inf")
    for spk_seg in rows:
        try:
            seg_start = float(spk_seg.get("start", 0.0) or 0.0)
            seg_end = float(spk_seg.get("end", seg_start) or seg_start)
        except Exception:
            continue
        if seg_start <= mid_time <= seg_end:
            return str(spk_seg.get("speaker") or closest_spk)
        dist = min(abs(mid_time - seg_start), abs(mid_time - seg_end))
        if dist < min_dist:
            min_dist = dist
            closest_spk = str(spk_seg.get("speaker") or closest_spk)
    return closest_spk


def build_inline_dialogue_speaker_split(
    row: dict[str, Any],
    speaker_map: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    *,
    fallback_speakers: tuple[str, str] = ("00", "01"),
) -> dict[str, Any]:
    explicit_speakers: list[str] = []
    seen_speakers: set[str] = set()
    for item in list((row or {}).get("speaker_list") or []):
        speaker = normalize_runtime_speaker_id(item)
        if speaker and speaker not in seen_speakers:
            explicit_speakers.append(speaker)
            seen_speakers.add(speaker)
    mapped_speakers = speaker_sequence_for_range((row or {}).get("start", 0.0), (row or {}).get("end", 0.0), speaker_map)
    turns = inline_dialogue_turns(
        (row or {}).get("text", ""),
        allow_missing_leading_marker=(
            len(explicit_speakers) >= 2
            or len(set(mapped_speakers)) >= 2
            or bool((row or {}).get("_stt_speaker_marker_preserved"))
        ),
    )
    if len(turns) != 2:
        return dict(row or {})

    speakers = explicit_speakers[:2] or mapped_speakers
    if len(set(speakers)) < 2:
        try:
            start_sec = float((row or {}).get("start", 0.0) or 0.0)
            end_sec = max(start_sec, float((row or {}).get("end", start_sec) or start_sec))
            mid_sec = start_sec + ((end_sec - start_sec) / 2.0)
            first = normalize_runtime_speaker_id(speaker_for_segment(start_sec, mid_sec, speaker_map or []))
            second = normalize_runtime_speaker_id(speaker_for_segment(mid_sec, end_sec, speaker_map or []))
            if first != second:
                speakers = [first, second]
        except Exception:
            pass
    if len(set(speakers)) < 2:
        speakers = list(fallback_speakers)
    speakers = [normalize_runtime_speaker_id(item) for item in speakers[:2]]

    updated = dict(row or {})
    updated["speaker"] = speakers[0]
    updated["speaker_list"] = speakers[:2]
    updated["text"] = "\n".join(f"- {turn}" for turn in turns)
    updated["_speaker_dialogue_turn_split"] = {
        "task": "runtime_dialogue_turn_split",
        "turns": 2,
        "fallback_speakers": len(set(speakers[:2])) < 2,
    }
    return updated


@dataclass(frozen=True)
class SubtitleSpeakerDiarizationResult:
    schema: str
    rows: tuple[dict[str, Any], ...]
    inline_split_count: int
    speaker_map_count: int
    merge_gap_sec: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "rows": [dict(row) for row in self.rows],
            "inline_split_count": self.inline_split_count,
            "speaker_map_count": self.speaker_map_count,
            "merge_gap_sec": self.merge_gap_sec,
            "counts": {
                "rows": len(self.rows),
                "inline_splits": self.inline_split_count,
                "speaker_map": self.speaker_map_count,
            },
        }


def apply_runtime_speaker_diarization(
    segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    *,
    speaker_map: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    enabled: bool = True,
    fallback_speakers: tuple[str, str] = ("00", "01"),
    merge_gap_sec: float = 1.5,
) -> SubtitleSpeakerDiarizationResult:
    rows = [dict(seg) for seg in list(segments or []) if isinstance(seg, dict)]
    speaker_rows = _speaker_map_rows(speaker_map)
    merge_gap = float(merge_gap_sec or 1.5)
    if not rows or not enabled:
        return SubtitleSpeakerDiarizationResult(
            schema=SUBTITLE_SPEAKER_DIARIZATION_SCHEMA,
            rows=tuple(rows),
            inline_split_count=0,
            speaker_map_count=len(speaker_rows),
            merge_gap_sec=merge_gap,
        )

    diarized_rows: list[dict[str, Any]] = []
    inline_split_count = 0
    for seg in rows:
        row = dict(seg)
        if speaker_rows:
            row["speaker"] = normalize_runtime_speaker_id(
                speaker_for_segment(row.get("start", 0.0), row.get("end", 0.0), speaker_rows)
            )
        updated = build_inline_dialogue_speaker_split(row, speaker_rows, fallback_speakers=fallback_speakers)
        if updated.get("text") != row.get("text"):
            inline_split_count += 1
        diarized_rows.append(updated)

    grouped_rows: list[dict[str, Any]] = []
    for row in diarized_rows:
        speaker_list = [
            normalize_runtime_speaker_id(item)
            for item in list(row.get("speaker_list") or [])
            if normalize_runtime_speaker_id(item)
        ]
        if len(set(speaker_list)) >= 2:
            row["speaker_list"] = speaker_list[:2]
            row["speaker"] = speaker_list[0]
            grouped_rows.append(row)
            continue

        line_parts = [
            line.strip().lstrip("-").strip()
            for line in str(row.get("text", "") or "").splitlines()
            if line.strip()
        ]
        flat_text = " ".join(part for part in line_parts if part)
        if not flat_text:
            continue
        speaker = normalize_runtime_speaker_id(row.get("speaker"))
        if grouped_rows:
            prev = grouped_rows[-1]
            prev_speakers = [
                normalize_runtime_speaker_id(item)
                for item in list(prev.get("speaker_list") or [])
                if normalize_runtime_speaker_id(item)
            ]
            gap = float(row.get("start", 0.0) or 0.0) - float(prev.get("end", 0.0) or 0.0)
            if (
                gap < merge_gap
                and prev_speakers
                and len(set(prev_speakers)) == 1
                and speaker != prev_speakers[-1]
                and len(prev_speakers) < 2
            ):
                prev.setdefault("text_list", [str(prev.get("text", "") or "").strip()])
                prev["text_list"].append(flat_text)
                prev["speaker_list"] = prev_speakers + [speaker]
                prev["end"] = max(float(prev.get("end", 0.0) or 0.0), float(row.get("end", 0.0) or 0.0))
                continue

        grouped_rows.append(
            {
                **row,
                "speaker": speaker,
                "speaker_list": [speaker],
                "text_list": [flat_text],
            }
        )

    finalized_rows: list[dict[str, Any]] = []
    for row in grouped_rows:
        item = dict(row)
        text_list = [str(part).strip() for part in list(item.get("text_list") or []) if str(part).strip()]
        speaker_list = [
            normalize_runtime_speaker_id(part)
            for part in list(item.get("speaker_list") or [])
            if normalize_runtime_speaker_id(part)
        ]
        if text_list:
            if len(set(speaker_list)) >= 2 and len(text_list) >= 2:
                item["text"] = "\n".join(f"- {part}" for part in text_list[:2])
                item["speaker_list"] = speaker_list[:2]
                item["speaker"] = item["speaker_list"][0]
            else:
                item["text"] = text_list[0]
                item["speaker_list"] = speaker_list[:1] or [normalize_runtime_speaker_id(item.get("speaker"))]
                item["speaker"] = item["speaker_list"][0]
        item.pop("text_list", None)
        finalized_rows.append(item)

    return SubtitleSpeakerDiarizationResult(
        schema=SUBTITLE_SPEAKER_DIARIZATION_SCHEMA,
        rows=tuple(finalized_rows),
        inline_split_count=inline_split_count,
        speaker_map_count=len(speaker_rows),
        merge_gap_sec=merge_gap,
    )


__all__ = [
    "SUBTITLE_SPEAKER_DIARIZATION_SCHEMA",
    "SubtitleSpeakerDiarizationResult",
    "apply_runtime_speaker_diarization",
    "build_inline_dialogue_speaker_split",
    "dialogue_turn_speaker_pair",
    "inline_dialogue_turns",
    "normalize_runtime_speaker_id",
    "speaker_for_segment",
    "speaker_sequence_for_range",
]
