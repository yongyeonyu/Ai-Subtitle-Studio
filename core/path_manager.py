# Version: 02.02.01
# Phase: PHASE1-B
"""
core/path_manager.py
[수정] 들여쓰기 에러(IndentationError) 해결 및 음성 파일 확장자 지원 추가
"""
import os
import json
import subprocess
import time
from logger import get_logger

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_FILE = os.path.join(ROOT_DIR, "dataset", "folder_settings.json")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_SETTINGS = {
    "watch_folders": [],
    "fcpxml_output": os.path.join(ROOT_DIR, "output", "FCPXML"), 
    "last_folder": "",
    "nas_urls": {},
    "nas_path": "",
    "icloud_path": "",
    "recent_folders": [],
    "auto_detect_enabled": False 
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for k, v in DEFAULT_SETTINGS.items():
                if k not in data:
                    data[k] = v
            return data
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

def get_last_folder(): return load_settings().get("last_folder", "")
def set_last_folder(path): s = load_settings(); s["last_folder"] = path; save_settings(s)

def get_nas_path(): return load_settings().get("nas_path", "")
def set_nas_path(path): s = load_settings(); s["nas_path"] = path; save_settings(s)

def get_icloud_path(): return load_settings().get("icloud_path", "")
def set_icloud_path(path): s = load_settings(); s["icloud_path"] = path; save_settings(s)

def get_auto_detect(): return load_settings().get("auto_detect_enabled", False)
def set_auto_detect(enabled: bool): s = load_settings(); s["auto_detect_enabled"] = enabled; save_settings(s)

def get_watch_folders(): return load_settings().get("watch_folders", [])
def add_watch_folder(path):
    settings = load_settings()
    if path not in settings["watch_folders"]:
        settings["watch_folders"].append(path); save_settings(settings)
def remove_watch_folder(path):
    settings = load_settings()
    settings["watch_folders"] = [f for f in settings["watch_folders"] if f != path]; save_settings(settings)

def get_fcpxml_output(): return load_settings().get("fcpxml_output", DEFAULT_SETTINGS["fcpxml_output"])

def _parse_smb_url(url):
    clean = url.replace("smb://", "")
    parts = clean.split("/")
    host = parts[0]
    share = parts[1] if len(parts) > 1 else "video"
    return host, share

def get_local_path(path):
    if path.startswith("smb://"):
        host, share = _parse_smb_url(path)
        return f"/Volumes/{share}"
    return path

def ensure_nas_mounted(folder_path):
    if not folder_path: return True
    if folder_path.startswith("smb://"):
        host, share = _parse_smb_url(folder_path)
        vol_path = f"/Volumes/{share}"
        if os.path.exists(vol_path): return True
        
        get_logger().log(f"  🔌 네트워크 NAS 자동 마운트 중: {folder_path}")
        subprocess.run(["osascript", "-e", f'mount volume "{folder_path}"'], capture_output=True)
        for _ in range(10):
            time.sleep(1)
            if os.path.exists(vol_path):
                get_logger().log(f"  ✅ NAS 마운트 완료: {vol_path}")
                return True
        get_logger().log(f"  ❌ NAS 마운트 실패. 경로를 확인해주세요.")
        return False
    return True

def get_video_files(folder, recursive=False):
    # 💡 이 아랫줄부터는 반드시 '탭'이나 '공백 4칸'으로 안으로 들여써야 합니다!
    exts = {'.mov', '.mp4', '.lrf', '.mp3', '.wav', '.m4a'}
    files = []
    def scan(path):
        try:
            with os.scandir(path) as it:
                for entry in it:
                    if entry.name.startswith('.'): continue
                    if entry.is_dir(follow_symlinks=False) and recursive: 
                        scan(entry.path)
                    elif entry.is_file(follow_symlinks=False) and os.path.splitext(entry.name)[1] in exts:
                        try: files.append((entry.stat().st_mtime, entry.path))
                        except: pass
        except PermissionError: pass
    scan(folder)
    files.sort()
    return [f for _, f in files]

def get_srt_path(video_path, suffix=""):
    base = os.path.splitext(video_path)[0]
    return f"{base}.srt" if not suffix else f"{base}_{suffix}.srt"

def get_pending_videos(folder, video_files):
    pending = []
    for vf in video_files:
        srt = get_srt_path(vf)
        if not os.path.exists(srt): 
            pending.append(vf)
        elif os.path.getmtime(vf) > os.path.getmtime(srt): 
            pending.append(vf)
    return pending

def get_recent_folders():
    return load_settings().get("recent_folders", [])

def add_recent_folder(path):
    if not path or not str(path).strip(): return
    settings = load_settings()
    recent = settings.get("recent_folders", [])
    if path in recent:
        recent.remove(path)
    recent.insert(0, path)
    settings["recent_folders"] = recent[:3]  
    save_settings(settings)
    
# 💡 [수정 완료] 진짜 함수 이름인 load_settings / save_settings로 연결했습니다.
def get_icloud_auto_detect() -> bool:
    settings = load_settings() 
    return settings.get("icloud_auto_detect", False)

def set_icloud_auto_detect(is_active: bool):
    settings = load_settings()
    settings["icloud_auto_detect"] = is_active
    save_settings(settings)

def get_nas_auto_detect() -> bool:
    settings = load_settings()
    return settings.get("nas_auto_detect", False)

def set_nas_auto_detect(is_active: bool):
    settings = load_settings()
    settings["nas_auto_detect"] = is_active
    save_settings(settings)