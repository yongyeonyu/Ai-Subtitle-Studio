from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core.personalization.lora_models import (
    ExcludedParentheticalRow,
    TruthTableRow,
    line_break_pattern_for_text,
    normalize_text,
    stable_hash,
)
from core.personalization.lora_storage import append_excluded_parentheticals, append_truth_table_rows
from core.srt_parser import parse_srt
from core.utils import load_rules


MEDIA_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg",
    ".mp4", ".mov", ".mkv", ".avi", ".wmv", ".mxf",
}
SUBTITLE_EXTENSIONS = {".srt"}
OPEN_TO_CLOSE = {"(": ")", "[": "]", "{": "}", "(": ")", "（": "）", "【": "】"}
CLOSE_TO_OPEN = {value: key for key, value in OPEN_TO_CLOSE.items()}


def _normalize_basename(value: str) -> str:
    return re.sub(r"[\W_]+", "", str(value or "").casefold())


def _clean_line_spaces(text: str) -> str:
    lines = []
    for line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        collapsed = re.sub(r"\s+", " ", line).strip()
        if collapsed:
            lines.append(collapsed)
    return "\n".join(lines)


def _contains_spoken_chars(text: str) -> bool:
    return bool(re.search(r"[0-9A-Za-z가-힣]", str(text or "")))


def extract_parenthetical_segments(text: str) -> dict[str, Any]:
    raw = str(text or "")
    kept_chars: list[str] = []
    excluded_blocks: list[str] = []
    stack: list[tuple[str, list[str]]] = []

    for char in raw:
        if char in OPEN_TO_CLOSE:
            stack.append((OPEN_TO_CLOSE[char], []))
            continue
        if stack:
            expected_close, buffer = stack[-1]
            if char == expected_close:
                excluded_text = "".join(buffer).strip()
                if excluded_text:
                    excluded_blocks.append(excluded_text)
                stack.pop()
                continue
            buffer.append(char)
            stack[-1] = (expected_close, buffer)
            continue
        kept_chars.append(char)

    for expected_close, buffer in stack:
        kept_chars.append(CLOSE_TO_OPEN.get(expected_close, "("))
        kept_chars.extend(buffer)

    kept_text = _clean_line_spaces("".join(kept_chars))
    excluded_text = " | ".join(block for block in excluded_blocks if block)
    return {
        "raw_text": raw.strip(),
        "speech_training_text": kept_text,
        "excluded_parenthetical_text": excluded_text,
        "had_parenthetical": bool(excluded_blocks),
    }


def _detect_split_rule(text: str) -> str:
    split_rules, _, _ = load_rules()
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    for line in lines[:-1]:
        last_token = re.split(r"\s+", line)[-1].strip(".,!?~")
        if 1 <= len(last_token) <= 12:
            return last_token
        for rule in sorted(split_rules, key=len, reverse=True):
            if line.endswith(str(rule or "").strip()):
                return str(rule).strip()
    return ""


def _punctuation_pattern(text: str) -> str:
    return "".join(ch for ch in str(text or "") if ch in ".,!?~")


def build_truth_table_records_from_srt(
    media_path: str | Path,
    subtitle_path: str | Path,
    *,
    media_id: str | None = None,
    speaker_or_voice_hint: str = "",
) -> dict[str, Any]:
    media_path = str(media_path)
    subtitle_path = str(subtitle_path)
    media_id = str(media_id or stable_hash({"media_path": media_path})[:16])
    truth_rows: list[dict[str, Any]] = []
    excluded_rows: list[dict[str, Any]] = []
    stats = {
        "segments_total": 0,
        "truth_rows": 0,
        "excluded_parenthetical_rows": 0,
        "skipped_empty_text": 0,
        "skipped_pure_symbols": 0,
    }

    for index, segment in enumerate(parse_srt(subtitle_path), start=1):
        stats["segments_total"] += 1
        raw_text = str(segment.get("text") or "").strip()
        if not raw_text:
            stats["skipped_empty_text"] += 1
            continue

        extracted = extract_parenthetical_segments(raw_text)
        speech_text = str(extracted["speech_training_text"] or "")
        excluded_text = str(extracted["excluded_parenthetical_text"] or "")
        segment_id = f"{Path(subtitle_path).stem}:{index}"

        if excluded_text:
            excluded_rows.append(
                ExcludedParentheticalRow(
                    media_id=media_id,
                    media_path=media_path,
                    subtitle_path=subtitle_path,
                    segment_id=segment_id,
                    original_text=raw_text,
                    excluded_text=excluded_text,
                    kept_text=speech_text,
                ).to_record()
            )
            stats["excluded_parenthetical_rows"] += 1

        if not speech_text:
            stats["skipped_empty_text"] += 1
            continue
        if not _contains_spoken_chars(speech_text):
            stats["skipped_pure_symbols"] += 1
            continue

        truth_rows.append(
            TruthTableRow(
                media_id=media_id,
                media_path=media_path,
                subtitle_path=subtitle_path,
                segment_id=segment_id,
                start_sec=float(segment.get("start", 0.0) or 0.0),
                end_sec=float(segment.get("end", 0.0) or 0.0),
                raw_ground_truth_text=raw_text,
                speech_training_text=speech_text,
                excluded_parenthetical_text=excluded_text,
                line_break_pattern=line_break_pattern_for_text(speech_text),
                punctuation_pattern=_punctuation_pattern(raw_text),
                detected_split_rule=_detect_split_rule(speech_text),
                speaker_or_voice_hint=speaker_or_voice_hint,
            ).to_record()
        )
        stats["truth_rows"] += 1

    return {
        "media_id": media_id,
        "media_path": media_path,
        "subtitle_path": subtitle_path,
        "truth_rows": truth_rows,
        "excluded_rows": excluded_rows,
        "stats": stats,
    }


def is_media_path(path: str | Path) -> bool:
    return Path(path).suffix.lower() in MEDIA_EXTENSIONS


def is_subtitle_path(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUBTITLE_EXTENSIONS


def discover_ground_truth_assets(inputs: list[str | Path]) -> dict[str, list[str]]:
    media_paths: list[str] = []
    subtitle_paths: list[str] = []
    for item in inputs or []:
        target = Path(item)
        candidates = [target]
        if target.is_dir():
            candidates = [path for path in target.rglob("*") if path.is_file()]
        for candidate in candidates:
            suffix = candidate.suffix.lower()
            if suffix in MEDIA_EXTENSIONS:
                media_paths.append(str(candidate))
            elif suffix in SUBTITLE_EXTENSIONS:
                subtitle_paths.append(str(candidate))
    return {
        "media_paths": sorted(set(media_paths)),
        "subtitle_paths": sorted(set(subtitle_paths)),
    }


def pair_media_and_subtitle_paths(
    media_paths: list[str | Path],
    subtitle_paths: list[str | Path],
) -> dict[str, Any]:
    subtitle_candidates = [str(Path(path)) for path in subtitle_paths or []]
    remaining_subtitles = set(subtitle_candidates)
    exact_index: dict[str, list[str]] = {}
    normalized_index: dict[str, list[str]] = {}
    for subtitle_path in subtitle_candidates:
        stem = Path(subtitle_path).stem
        exact_index.setdefault(stem, []).append(subtitle_path)
        normalized_index.setdefault(_normalize_basename(stem), []).append(subtitle_path)

    pairs: list[dict[str, str]] = []
    unmatched_media: list[str] = []
    ambiguous_matches: list[dict[str, Any]] = []

    for media_path in sorted(str(Path(path)) for path in media_paths or []):
        stem = Path(media_path).stem
        exact_matches = [path for path in exact_index.get(stem, []) if path in remaining_subtitles]
        if len(exact_matches) == 1:
            subtitle_path = exact_matches[0]
            remaining_subtitles.remove(subtitle_path)
            pairs.append({"media_path": media_path, "subtitle_path": subtitle_path, "match_type": "exact"})
            continue
        if len(exact_matches) > 1:
            ambiguous_matches.append(
                {"media_path": media_path, "subtitle_candidates": exact_matches, "match_type": "exact"}
            )
            continue

        normalized_matches = [
            path for path in normalized_index.get(_normalize_basename(stem), []) if path in remaining_subtitles
        ]
        if len(normalized_matches) == 1:
            subtitle_path = normalized_matches[0]
            remaining_subtitles.remove(subtitle_path)
            pairs.append({"media_path": media_path, "subtitle_path": subtitle_path, "match_type": "normalized"})
            continue
        if len(normalized_matches) > 1:
            ambiguous_matches.append(
                {"media_path": media_path, "subtitle_candidates": normalized_matches, "match_type": "normalized"}
            )
            continue
        unmatched_media.append(media_path)

    return {
        "pairs": pairs,
        "unmatched_media_paths": unmatched_media,
        "unmatched_subtitle_paths": sorted(remaining_subtitles),
        "ambiguous_matches": ambiguous_matches,
    }


def pair_ground_truth_assets(inputs: list[str | Path]) -> dict[str, Any]:
    assets = discover_ground_truth_assets(inputs)
    return {
        **assets,
        **pair_media_and_subtitle_paths(assets["media_paths"], assets["subtitle_paths"]),
    }


def resolve_ambiguous_matches(
    ambiguous_matches: list[dict[str, Any]],
    chooser,
) -> dict[str, Any]:
    resolved_pairs: list[dict[str, str]] = []
    unresolved: list[dict[str, Any]] = []

    for item in list(ambiguous_matches or []):
        media_path = str(item.get("media_path") or "")
        match_type = str(item.get("match_type") or "ambiguous")
        candidates = [str(Path(path)) for path in list(item.get("subtitle_candidates") or []) if str(path or "").strip()]
        if not media_path or not candidates:
            unresolved.append(dict(item))
            continue

        selected = chooser(media_path, candidates, match_type) if callable(chooser) else None
        selected_key = str(Path(str(selected))) if selected else ""
        selected_path = next((candidate for candidate in candidates if str(Path(candidate)) == selected_key), "")
        if selected_path:
            resolved_pairs.append(
                {
                    "media_path": media_path,
                    "subtitle_path": selected_path,
                    "match_type": f"user_confirmed_{match_type}",
                }
            )
            continue
        unresolved.append(dict(item))

    return {
        "pairs": resolved_pairs,
        "unresolved": unresolved,
    }


def import_ground_truth_pairs(
    pairs: list[dict[str, Any]],
    *,
    store_dir: str | Path | None = None,
) -> dict[str, Any]:
    imported_pairs = 0
    truth_total = 0
    excluded_total = 0
    skipped_total = 0

    for pair in pairs or []:
        result = build_truth_table_records_from_srt(
            pair.get("media_path", ""),
            pair.get("subtitle_path", ""),
            media_id=str(pair.get("media_id") or ""),
            speaker_or_voice_hint=str(pair.get("speaker_or_voice_hint") or ""),
        )
        append_truth_table_rows(result["truth_rows"], store_dir)
        append_excluded_parentheticals(result["excluded_rows"], store_dir)
        imported_pairs += 1
        truth_total += int(result["stats"]["truth_rows"])
        excluded_total += int(result["stats"]["excluded_parenthetical_rows"])
        skipped_total += int(result["stats"]["skipped_empty_text"]) + int(result["stats"]["skipped_pure_symbols"])

    return {
        "imported_pairs": imported_pairs,
        "truth_rows": truth_total,
        "excluded_rows": excluded_total,
        "skipped_rows": skipped_total,
    }


__all__ = [
    "MEDIA_EXTENSIONS",
    "SUBTITLE_EXTENSIONS",
    "build_truth_table_records_from_srt",
    "discover_ground_truth_assets",
    "extract_parenthetical_segments",
    "import_ground_truth_pairs",
    "is_media_path",
    "is_subtitle_path",
    "pair_ground_truth_assets",
    "pair_media_and_subtitle_paths",
    "resolve_ambiguous_matches",
]
