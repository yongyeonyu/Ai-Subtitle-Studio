# Version: 02.00.00
"""
core/project_manager.py
프로젝트 JSON 파일 생성 / 저장 / 로드
[v02.00.00] Phase2 대비 timeline 구조 + ffprobe duration 자동 계산
"""
import os, json, subprocess, uuid
from datetime import datetime

PROJECTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "projects")


def ensure_projects_dir():
    os.makedirs(PROJECTS_DIR, exist_ok=True)


def _get_media_duration(filepath: str) -> float:
    """ffprobe로 미디어 길이(초) 반환"""
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', filepath],
            capture_output=True, text=True, timeout=10)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def _make_clip_id() -> str:
    return f"clip_{uuid.uuid4().hex[:8]}"


def _make_seg_id() -> str:
    return f"seg_{uuid.uuid4().hex[:8]}"


def create_project(name: str, media_paths: list = None, srt_path: str = None, user_settings: dict = None) -> str:
    """새 프로젝트 JSON 생성 (v2 timeline 구조) → 파일 경로 반환"""
    ensure_projects_dir()
    now = datetime.now().isoformat()
    
    # 클립 생성 + duration 자동 계산
    clips = []
    cumulative = 0.0
    if media_paths:
        for i, p in enumerate(media_paths):
            ext = os.path.splitext(p)[1].lower()
            m_type = "audio" if ext in {'.wav', '.m4a', '.mp3', '.aac', '.m2a'} else "video"
            dur = _get_media_duration(p)
            clips.append({
                "id": _make_clip_id(),
                "source_path": p,
                "type": m_type,
                "source_duration": dur,
                "in_point": 0.0,
                "out_point": dur,
                "timeline_start": cumulative,
                "timeline_end": cumulative + dur,
                "order": i
            })
            cumulative += dur

    # SRT 파싱
    segments = []
    if srt_path and os.path.exists(srt_path):
        raw_segs = _parse_srt_to_segments(srt_path)
        for seg in raw_segs:
            clip_id = ""
            clip_local_start = seg["start"]
            clip_local_end = seg["end"]
            # 자막이 어느 클립에 속하는지 매칭
            for c in clips:
                if c["timeline_start"] <= seg["start"] < c["timeline_end"]:
                    clip_id = c["id"]
                    clip_local_start = seg["start"] - c["timeline_start"]
                    clip_local_end = seg["end"] - c["timeline_start"]
                    break
            seg["id"] = _make_seg_id()
            seg["clip_id"] = clip_id
            seg["clip_local_start"] = clip_local_start
            seg["clip_local_end"] = clip_local_end
            seg["timeline_start"] = seg.pop("start")
            seg["timeline_end"] = seg.pop("end")
            seg["speaker"] = seg.get("speaker", "00")
            seg["is_deleted"] = False
            segments.append(seg)

    project = {
        "app": "AI Subtitle Studio",
        "version": "02.00.00",
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

        "edit_history": {
            "last_playhead": 0.0,
            "last_active_clip": clips[0]["id"] if clips else "",
            "zoom_level": 50.0,
            "scroll_position": 0.0
        },

        "user_settings": user_settings or {},

        # 하위 호환용 (기존 코드에서 media[] 참조하는 곳 대비)
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

    # 파일명 충돌 방지
    filename = f"{name}.json"
    filepath = os.path.join(PROJECTS_DIR, filename)
    counter = 1
    while os.path.exists(filepath):
        filename = f"{name}_{counter}.json"
        filepath = os.path.join(PROJECTS_DIR, filename)
        counter += 1

    _write_json(filepath, project)
    return filepath


def save_project(filepath: str, media_paths: list = None, srt_path: str = None,
                 segments: list = None, user_settings: dict = None):
    """기존 프로젝트 JSON 업데이트"""
    if not os.path.exists(filepath):
        return

    project = _read_json(filepath)
    project["updated_at"] = datetime.now().isoformat()

    if media_paths is not None:
        clips = []
        cumulative = 0.0
        for i, p in enumerate(media_paths):
            ext = os.path.splitext(p)[1].lower()
            m_type = "audio" if ext in {'.wav', '.m4a', '.mp3', '.aac', '.m2a'} else "video"
            dur = _get_media_duration(p)
            clips.append({
                "id": _make_clip_id(),
                "source_path": p,
                "type": m_type,
                "source_duration": dur,
                "in_point": 0.0,
                "out_point": dur,
                "timeline_start": cumulative,
                "timeline_end": cumulative + dur,
                "order": i
            })
            cumulative += dur

        if "timeline" not in project:
            project["timeline"] = {"total_duration": 0.0, "tracks": []}
        project["timeline"]["total_duration"] = cumulative
        if project["timeline"]["tracks"]:
            project["timeline"]["tracks"][0]["clips"] = clips
        else:
            project["timeline"]["tracks"] = [{"id": "video_track_0", "type": "video", "clips": clips}]

        # 하위 호환
        project["media"] = [
            {"order": c["order"], "path": c["source_path"], "type": c["type"],
             "duration": c["source_duration"], "offset": c["timeline_start"]}
            for c in clips
        ]

    if srt_path is not None:
        if "subtitles" not in project:
            project["subtitles"] = {"srt_path": "", "segments": []}
        project["subtitles"]["srt_path"] = srt_path
        # 하위 호환
        if "subtitle" in project:
            project["subtitle"]["path"] = srt_path

    if segments is not None:
        # 클립 정보 가져오기
        clips = []
        if "timeline" in project and project["timeline"].get("tracks"):
            clips = project["timeline"]["tracks"][0].get("clips", [])

        new_segs = []
        for i, seg in enumerate(segments):
            clip_id = ""
            t_start = seg.get("timeline_start", seg.get("start", 0.0))
            t_end = seg.get("timeline_end", seg.get("end", 0.0))
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
                "srt_synced": True,
                "tags": seg.get("tags", []),
                "llm_note": seg.get("llm_note", ""),
                "is_deleted": seg.get("is_deleted", False)
            })

        if "subtitles" not in project:
            project["subtitles"] = {"srt_path": "", "segments": []}
        project["subtitles"]["segments"] = new_segs

    if user_settings is not None:
        project["user_settings"] = user_settings

    _write_json(filepath, project)


def load_project(filepath: str) -> dict | None:
    """프로젝트 JSON 로드 → dict 반환"""
    if not os.path.exists(filepath):
        return None
    return _read_json(filepath)


def list_projects() -> list[dict]:
    """projects/ 폴더 내 모든 프로젝트 목록 반환 (최근 수정순)"""
    ensure_projects_dir()
    result = []
    for f in os.listdir(PROJECTS_DIR):
        if not f.endswith(".json"):
            continue
        fp = os.path.join(PROJECTS_DIR, f)
        try:
            data = _read_json(fp)
            media_count = 0
            if "timeline" in data and data["timeline"].get("tracks"):
                media_count = len(data["timeline"]["tracks"][0].get("clips", []))
            elif "media" in data:
                media_count = len(data["media"])
            result.append({
                "name": data.get("project_name", f),
                "path": fp,
                "updated_at": data.get("updated_at", ""),
                "media_count": media_count
            })
        except Exception:
            continue
    result.sort(key=lambda x: x["updated_at"], reverse=True)
    return result


def add_media_to_project(filepath: str, new_paths: list):
    """기존 프로젝트에 미디어 파일 추가"""
    if not os.path.exists(filepath):
        return
    
    project = _read_json(filepath)
    
    # timeline 구조에서 클립 가져오기
    clips = []
    if "timeline" in project and project["timeline"].get("tracks"):
        clips = project["timeline"]["tracks"][0].get("clips", [])
    
    existing_paths = {c["source_path"] for c in clips}
    max_order = max((c.get("order", 0) for c in clips), default=-1)
    
    # 마지막 클립의 timeline_end가 새 클립의 시작점
    cumulative = max((c.get("timeline_end", 0.0) for c in clips), default=0.0)
    
    for p in new_paths:
        if p in existing_paths:
            continue
        max_order += 1
        ext = os.path.splitext(p)[1].lower()
        m_type = "audio" if ext in {'.wav', '.m4a', '.mp3', '.aac', '.m2a'} else "video"
        dur = _get_media_duration(p)
        clips.append({
            "id": _make_clip_id(),
            "source_path": p,
            "type": m_type,
            "source_duration": dur,
            "in_point": 0.0,
            "out_point": dur,
            "timeline_start": cumulative,
            "timeline_end": cumulative + dur,
            "order": max_order
        })
        cumulative += dur
    
    if "timeline" not in project:
        project["timeline"] = {"total_duration": 0.0, "tracks": []}
    project["timeline"]["total_duration"] = cumulative
    if project["timeline"]["tracks"]:
        project["timeline"]["tracks"][0]["clips"] = clips
    else:
        project["timeline"]["tracks"] = [{"id": "video_track_0", "type": "video", "clips": clips}]
    
    # 하위 호환
    project["media"] = [
        {"order": c["order"], "path": c["source_path"], "type": c["type"],
         "duration": c["source_duration"], "offset": c["timeline_start"]}
        for c in clips
    ]
    
    project["updated_at"] = datetime.now().isoformat()
    _write_json(filepath, project)


def merge_srt_to_project(filepath: str):
    """프로젝트 내 각 클립의 개별 SRT를 찾아서 segments에 병합"""
    if not os.path.exists(filepath):
        return
    
    project = _read_json(filepath)
    
    clips = []
    if "timeline" in project and project["timeline"].get("tracks"):
        clips = sorted(project["timeline"]["tracks"][0].get("clips", []), key=lambda x: x.get("order", 0))
    
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
                "srt_synced": True,
                "tags": [],
                "llm_note": "",
                "is_deleted": False
            })
    
    if "subtitles" not in project:
        project["subtitles"] = {"srt_path": "", "segments": []}
    project["subtitles"]["segments"] = all_segments
    project["updated_at"] = datetime.now().isoformat()
    _write_json(filepath, project)
    
    return len(all_segments)


def get_boundary_times(project: dict) -> list[float]:
    """프로젝트에서 클립 경계 시간 리스트 반환 (마지막 제외)"""
    clips = []
    if "timeline" in project and project["timeline"].get("tracks"):
        clips = sorted(project["timeline"]["tracks"][0].get("clips", []), key=lambda x: x.get("order", 0))
    elif "media" in project:
        clips = sorted(project["media"], key=lambda x: x.get("order", 0))
    
    boundaries = []
    for c in clips:
        end = c.get("timeline_end", 0.0)
        if end <= 0:
            end = c.get("offset", 0.0) + c.get("duration", 0.0)
        if end > 0:
            boundaries.append(end)
    
    # 마지막 경계 제거 (전체 끝과 동일)
    if boundaries:
        boundaries.pop()
    
    return boundaries


# ── 내부 유틸 ──

def _read_json(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(filepath: str, data: dict):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _parse_srt_to_segments(srt_path: str) -> list[dict]:
    """SRT → 세그먼트 리스트"""
    import re
    segments = []
    content = ""
    for enc in ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr']:
        try:
            with open(srt_path, "r", encoding=enc) as f:
                content = f.read()
            break
        except UnicodeDecodeError:
            continue
    if not content:
        return segments

    content = content.replace('\r\n', '\n').replace('\r', '\n')
    pattern = re.compile(
        r'(\d{2}:\d{2}:\d{2}[,.]\d{2,3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{2,3})\n(.*?)(?=\n(?:\s*\d+\s*\n)?\s*\d{2}:\d{2}:\d{2}[,.]|\Z)',
        re.DOTALL
    )

    def srt_to_sec(ts):
        h, mn, s = ts.replace(',', '.').split(':')
        return int(h) * 3600 + int(mn) * 60 + float(s)

    for i, m in enumerate(pattern.finditer(content)):
        try:
            segments.append({
                "index": i + 1,
                "start": srt_to_sec(m.group(1)),
                "end": srt_to_sec(m.group(2)),
                "text": m.group(3).strip(),
                "media_index": 0,
                "srt_synced": True,
                "tags": [],
                "llm_note": ""
            })
        except Exception:
            continue
    return segments