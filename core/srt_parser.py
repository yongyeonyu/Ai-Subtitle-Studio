# Version: 02.02.01
# Phase: PHASE1-B
"""
core/srt_parser.py
SRT 파일 파싱 유틸
- main_window._parse_srt_file() + editor_widget._fallback_parse_srt() 통합
- 블록 단위 파싱 (멀티라인 자막 정상 처리)
"""

import re
import os


def parse_srt(srt_path: str) -> list:
    """
    SRT 파일을 파싱하여 세그먼트 리스트 반환.
    [{"start": float, "end": float, "text": str, "is_gap": False}, ...]
    """
    segments = []
    if not os.path.exists(srt_path):
        return segments

    content = ""
    for enc in ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr']:
        try:
            with open(srt_path, "r", encoding=enc) as f:
                content = f.read()
            break
        except (UnicodeDecodeError, Exception):
            continue

    if not content:
        return segments

    content = content.replace('\r\n', '\n').replace('\r', '\n')

    blocks = re.split(r'\n\s*\n', content.strip())
    ts_re = re.compile(
        r'(\d{2}:\d{2}:\d{2}[,.]\d{2,3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{2,3})'
    )

    def _ts(ts):
        h, mn, s = ts.replace(',', '.').split(':')
        return int(h) * 3600 + int(mn) * 60 + float(s)

    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 2:
            continue

        ts_line_idx = None
        for i, line in enumerate(lines):
            if ts_re.search(line):
                ts_line_idx = i
                break
        if ts_line_idx is None:
            continue

        m = ts_re.search(lines[ts_line_idx])
        if not m:
            continue

        text_lines = lines[ts_line_idx + 1:]
        text = '\n'.join(text_lines).strip()
        if not text:
            continue

        try:
            segments.append({
                "start": _ts(m.group(1)),
                "end": _ts(m.group(2)),
                "text": text,
                "is_gap": False
            })
        except Exception:
            continue

    return segments