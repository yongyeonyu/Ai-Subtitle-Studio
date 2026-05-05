from __future__ import annotations

import re


def parse_srt_to_segments(srt_path: str) -> list[dict]:
    """Convert an SRT file into project segment dictionaries."""
    segments: list[dict] = []
    content = ""
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            with open(srt_path, "r", encoding=encoding) as handle:
                content = handle.read()
            break
        except UnicodeDecodeError:
            continue

    if not content:
        return segments

    content = content.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", content.strip())
    timestamp_re = re.compile(r"(\d{2}:\d{2}:\d{2}[,.]\d{2,3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{2,3})")

    def srt_to_sec(timestamp: str) -> float:
        hours, minutes, seconds = timestamp.replace(",", ".").split(":")
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 2:
            continue

        timestamp_line_index = next((index for index, line in enumerate(lines) if timestamp_re.search(line)), None)
        if timestamp_line_index is None:
            continue

        match = timestamp_re.search(lines[timestamp_line_index])
        if not match:
            continue

        text = "\n".join(lines[timestamp_line_index + 1:]).strip()
        if not text:
            continue

        try:
            segments.append(
                {
                    "index": len(segments) + 1,
                    "start": srt_to_sec(match.group(1)),
                    "end": srt_to_sec(match.group(2)),
                    "text": text,
                    "tags": [],
                    "llm_note": "",
                    "srt_synced": True,
                }
            )
        except Exception:
            continue

    return segments
