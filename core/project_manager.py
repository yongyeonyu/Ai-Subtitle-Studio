# Version: 02.02.00
# Phase: PHASE1-B
"""
core/project_manager.py
프로젝트 JSON 파일 생성 / 저장 / 로드

[v02.01.00]
- 저장 시 workspace(작업 환경) 저장/복원 지원
- 자동 프로젝트 저장 흐름 대응
- 구조 정리 및 중복 코드 리팩토링
- v02.00.00 완전 하위 호환 유지
"""

import os
import json
import subprocess
import uuid
from datetime import datetime
from typing import List, Optional


# ─────────────────────────────────────────────
# 기본 경로
# ─────────────────────────────────────────────

PROJECTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "projects"
)


def ensure_projects_dir():
    os.makedirs(PROJECTS_DIR, exist_ok=True)


# ─────────────────────────────────────────────
# ID / Duration 유틸
# ─────────────────────────────────────────────

def _make_clip_id() -> str:
    return f"clip_{uuid.uuid4().hex[:8]}"


def _make_seg_id() -> str:
    return f"seg_{uuid.uuid4().hex[:8]}"


def _get_media_duration(filepath: str) -> float:
    """ffprobe로 미디어 길이(초) 반환"""
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                filepath
            ],
            capture_output=True,
            text=True,
            timeout=10
        )
        return float(r.stdout.strip())
    except Exception:
        return 0.0


# ─────────────────────────────────────────────
# 프로젝트 생성
# ─────────────────────────────────────────────

def create_project(
    name: str,
    media_paths: Optional[List[str]] = None,
    srt_path: Optional[str] = None,
    user_settings: Optional[dict] = None
) -> str:
    """새 프로젝트 JSON 생성 → 파일 경로 반환"""
    ensure_projects_dir()
    now = datetime.now().isoformat()

    clips = []
    cumulative = 0.0

    if media_paths:
        for i, path in enumerate(media_paths):
            ext = os.path.splitext(path)[1].lower()
            m_type = "audio" if ext in {".wav", ".m4a", ".mp3", ".aac", ".m2a"} else "video"
            dur = _get_media_duration(path)

            clips.append({
                "id": _make_clip_id(),
                "source_path": path,
                "type": m_type,
                "source_duration": dur,
                "in_point": 0.0,
                "out_point": dur,
                "timeline_start": cumulative,
                "timeline_end": cumulative + dur,
                "order": i
            })
            cumulative += dur

    segments = []
    if srt_path and os.path.exists(srt_path):
        raw_segs = _parse_srt_to_segments(srt_path)
        for seg in raw_segs:
            clip_id = ""
            cl_start = seg["start"]
            cl_end = seg["end"]

            for c in clips:
                if c["timeline_start"] <= seg["start"] < c["timeline_end"]:
                    clip_id = c["id"]
                    cl_start = seg["start"] - c["timeline_start"]
                    cl_end = seg["end"] - c["timeline_start"]
                    break

            segments.append({
                "id": _make_seg_id(),
                "index": seg.get("index", 0),
                "timeline_start": seg["start"],
                "timeline_end": seg["end"],
                "clip_id": clip_id,
                "clip_local_start": cl_start,
                "clip_local_end": cl_end,
                "text": seg.get("text", "").replace("\u2028", "\n"),
                "speaker": seg.get("speaker", "00"),
                "tags": seg.get("tags", []),
                "llm_note": seg.get("llm_note", ""),
                "srt_synced": True,
                "is_deleted": False
            })

    project = {
        "app": "AI Subtitle Studio",
        "version": "02.01.00",
        "project_name": name,
        "created_at": now,
        "updated_at": now,

        "timeline": {
            "total_duration": cumulative,
            "tracks": [
                {
                    "id": "video_track_0",
                    "type": "video",
                    "clips": clips
                }
            ]
        },

        "subtitles": {
            "srt_path": srt_path or "",
            "segments": segments
        },

        # ✅ [v02.01.00] 작업 환경 저장용
        "workspace": {
            "last_playhead": 0.0,
            "last_cursor_block": 0,
            "zoom_pps": 500.0,
            "scroll_position": 0.0,
            "splitter_sizes": [],
            "terminal_visible": False
        },

        "user_settings": user_settings or {},

        # 하위 호환용
        "media": [
            {
                "order": c["order"],
                "path": c["source_path"],
                "type": c["type"],
                "duration": c["source_duration"],
                "offset": c["timeline_start"]
            }
            for c in clips
        ]
    }

    filename = f"{name}.json"
    filepath = os.path.join(PROJECTS_DIR, filename)
    counter = 1
    while os.path.exists(filepath):
        filepath = os.path.join(PROJECTS_DIR, f"{name}_{counter}.json")
        counter += 1

    _write_json(filepath, project)
    return filepath


# ─────────────────────────────────────────────
# 프로젝트 저장
# ─────────────────────────────────────────────

def save_project(
    filepath: str,
    media_paths: Optional[List[str]] = None,
    srt_path: Optional[str] = None,
    segments: Optional[List[dict]] = None,
    user_settings: Optional[dict] = None,
    workspace: Optional[dict] = None
):
    """기존 프로젝트 JSON 업데이트"""
    if not os.path.exists(filepath):
        return

    project = _read_json(filepath)
    project["updated_at"] = datetime.now().isoformat()

    # ── 미디어 업데이트 ──
    if media_paths is not None:
        clips = []
        cumulative = 0.0
        for i, path in enumerate(media_paths):
            ext = os.path.splitext(path)[1].lower()
            m_type = "audio" if ext in {".wav", ".m4a", ".mp3", ".aac", ".m2a"} else "video"
            dur = _get_media_duration(path)
            clips.append({
                "id": _make_clip_id(),
                "source_path": path,
                "type": m_type,
                "source_duration": dur,
                "in_point": 0.0,
                "out_point": dur,
                "timeline_start": cumulative,
                "timeline_end": cumulative + dur,
                "order": i
            })
            cumulative += dur

        project.setdefault("timeline", {"tracks": []})
        project["timeline"]["total_duration"] = cumulative
        project["timeline"]["tracks"] = [{
            "id": "video_track_0",
            "type": "video",
            "clips": clips
        }]

        project["media"] = [
            {
                "order": c["order"],
                "path": c["source_path"],
                "type": c["type"],
                "duration": c["source_duration"],
                "offset": c["timeline_start"]
            }
            for c in clips
        ]

    # ── SRT 경로 ──
    if srt_path is not None:
        project.setdefault("subtitles", {})
        project["subtitles"]["srt_path"] = srt_path

    # ── 세그먼트 ──
    if segments is not None:
        clips = project.get("timeline", {}).get("tracks", [{}])[0].get("clips", [])
        new_segs = []

        for i, seg in enumerate(segments):
            t_start = seg.get("timeline_start", seg.get("start", 0.0))
            t_end = seg.get("timeline_end", seg.get("end", 0.0))

            clip_id = ""
            cl_start = t_start
            cl_end = t_end

            for c in clips:
                if c["timeline_start"] <= t_start < c["timeline_end"]:
                    clip_id = c["id"]
                    cl_start = t_start - c["timeline_start"]
                    cl_end = t_end - c["timeline_start"]
                    break

            new_segs.append({
                "id": seg.get("id", _make_seg_id()),
                "index": i + 1,
                "timeline_start": t_start,
                "timeline_end": t_end,
                "clip_id": clip_id,
                "clip_local_start": cl_start,
                "clip_local_end": cl_end,
                "text": seg.get("text", ""),
                "speaker": seg.get("speaker", "00"),
                "tags": seg.get("tags", []),
                "llm_note": seg.get("llm_note", ""),
                "srt_synced": True,
                "is_deleted": seg.get("is_deleted", False)
            })

        project.setdefault("subtitles", {})
        project["subtitles"]["segments"] = new_segs

    # ── 사용자 설정 ──
    if user_settings is not None:
        project["user_settings"] = user_settings

    # ── 작업 환경 ──
    if workspace is not None:
        project["workspace"] = workspace

    _write_json(filepath, project)


# ─────────────────────────────────────────────
# 로드 / 목록
# ─────────────────────────────────────────────

def load_project(filepath: str) -> dict | None:
    """프로젝트 JSON 로드 → dict 반환"""
    if not os.path.exists(filepath):
        return None
    return _read_json(filepath)


def list_projects() -> list:
    """projects/ 폴더 내 모든 프로젝트 목록 반환 (최근 수정순)"""
    ensure_projects_dir()
    result = []
    for fname in os.listdir(PROJECTS_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(PROJECTS_DIR, fname)
        try:
            data = _read_json(path)
            clips = data.get("timeline", {}).get("tracks", [{}])[0].get("clips", [])
            result.append({
                "name": data.get("project_name", fname),
                "path": path,
                "updated_at": data.get("updated_at", ""),
                "media_count": len(clips)
            })
        except Exception:
            continue
    result.sort(key=lambda x: x["updated_at"], reverse=True)
    return result


# ─────────────────────────────────────────────
# 경계선
# ─────────────────────────────────────────────

def get_boundary_times(project: dict) -> list:
    """프로젝트에서 클립 경계 시간 리스트 반환 (마지막 제외)"""
    clips = project.get("timeline", {}).get("tracks", [{}])[0].get("clips", [])
    boundaries = []
    for c in clips:
        end = c.get("timeline_end", 0.0)
        if end > 0:
            boundaries.append(end)
    if boundaries:
        boundaries.pop()
    return boundaries


# ─────────────────────────────────────────────
# 미디어 추가 / SRT 병합
# ─────────────────────────────────────────────

def add_media_to_project(filepath: str, new_paths: list):
    """기존 프로젝트에 미디어 파일 추가"""
    if not os.path.exists(filepath):
        return

    project = _read_json(filepath)

    clips = project.get("timeline", {}).get("tracks", [{}])[0].get("clips", [])
    existing_paths = {c["source_path"] for c in clips}
    max_order = max((c.get("order", 0) for c in clips), default=-1)
    cumulative = max((c.get("timeline_end", 0.0) for c in clips), default=0.0)

    for path in new_paths:
        if path in existing_paths:
            continue
        max_order += 1
        ext = os.path.splitext(path)[1].lower()
        m_type = "audio" if ext in {".wav", ".m4a", ".mp3", ".aac", ".m2a"} else "video"
        dur = _get_media_duration(path)
        clips.append({
            "id": _make_clip_id(),
            "source_path": path,
            "type": m_type,
            "source_duration": dur,
            "in_point": 0.0,
            "out_point": dur,
            "timeline_start": cumulative,
            "timeline_end": cumulative + dur,
            "order": max_order
        })
        cumulative += dur

    project.setdefault("timeline", {"tracks": []})
    project["timeline"]["total_duration"] = cumulative
    project["timeline"]["tracks"] = [{
        "id": "video_track_0",
        "type": "video",
        "clips": clips
    }]

    project["media"] = [
        {
            "order": c["order"],
            "path": c["source_path"],
            "type": c["type"],
            "duration": c["source_duration"],
            "offset": c["timeline_start"]
        }
        for c in clips
    ]

    project["updated_at"] = datetime.now().isoformat()
    _write_json(filepath, project)


def merge_srt_to_project(filepath: str) -> int | None:
    """프로젝트 내 각 클립의 개별 SRT를 찾아서 segments에 병합"""
    if not os.path.exists(filepath):
        return None

    project = _read_json(filepath)
    clips = sorted(
        project.get("timeline", {}).get("tracks", [{}])[0].get("clips", []),
        key=lambda x: x.get("order", 0)
    )

    all_segments = []
    for clip in clips:
        base = os.path.splitext(clip["source_path"])[0]
        srt_path = base + ".srt"
        if not os.path.exists(srt_path):
            continue

        raw_segs = _parse_srt_to_segments(srt_path)
        offset = clip["timeline_start"]

        for seg in raw_segs:
            all_segments.append({
                "id": _make_seg_id(),
                "index": len(all_segments) + 1,
                "timeline_start": seg["start"] + offset,
                "timeline_end": seg["end"] + offset,
                "clip_id": clip["id"],
                "clip_local_start": seg["start"],
                "clip_local_end": seg["end"],
                "text": seg.get("text", ""),
                "speaker": seg.get("speaker", "00"),
                "tags": [],
                "llm_note": "",
                "srt_synced": True,
                "is_deleted": False
            })

    project.setdefault("subtitles", {})
    project["subtitles"]["segments"] = all_segments
    project["updated_at"] = datetime.now().isoformat()
    _write_json(filepath, project)

    return len(all_segments)


# ─────────────────────────────────────────────
# 내부 유틸
# ─────────────────────────────────────────────

def _read_json(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(filepath: str, data: dict):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _parse_srt_to_segments(srt_path: str) -> list:
    """SRT → 세그먼트 리스트"""
    import re
    segments = []
    content = ""
    for enc in ["utf-8-sig", "utf-8", "cp949", "euc-kr"]:
        try:
            with open(srt_path, "r", encoding=enc) as f:
                content = f.read()
            break
        except UnicodeDecodeError:
            continue

    if not content:
        return segments

    content = content.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", content.strip())
    ts_re = re.compile(
        r"(\d{2}:\d{2}:\d{2}[,.]\d{2,3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{2,3})"
    )

    def srt_to_sec(ts):
        h, m, s = ts.replace(",", ".").split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    idx = 0
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 2:
            continue

        ts_line_idx = None
        for i, line in enumerate(lines):
            if ts_re.search(line):
                ts_line_idx = i
                break
        if ts_line_idx is None:
            continue

        match = ts_re.search(lines[ts_line_idx])
        if not match:
            continue

        text_lines = lines[ts_line_idx + 1:]
        text = "\n".join(text_lines).strip()
        if not text:
            continue

        idx += 1
        try:
            segments.append({
                "index": idx,
                "start": srt_to_sec(match.group(1)),
                "end": srt_to_sec(match.group(2)),
                "text": text,
                "tags": [],
                "llm_note": "",
                "srt_synced": True
            })
        except Exception:
            continue

    return segments