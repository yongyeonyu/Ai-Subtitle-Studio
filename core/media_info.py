# Version: 02.03.00
# Phase: PHASE1-B
"""
core/media_info.py
ffprobe 기반 미디어 정보 조회 유틸
"""
import json, subprocess


def probe_media(filepath: str) -> dict:
    """
    Returns: {duration, width, height, fps, info_txt, len_txt}
    """
    result = {
        "duration": 0.0, "width": 0, "height": 0, "fps": 0.0,
        "info_txt": "오디오 파일", "len_txt": "-"
    }
    try:
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate:format=duration",
            "-of", "json", filepath,
        ]
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=5
        )
        probe = json.loads(proc.stdout)
        fmt = probe.get("format", {})
        duration = float(fmt.get("duration", 0)) if fmt.get("duration") else 0.0
        streams = probe.get("streams", [])

        if streams:
            strm = streams[0]
            if duration == 0.0:
                duration = float(strm.get("duration", 0)) if strm.get("duration") else 0.0
            w, h = strm.get("width", 0), strm.get("height", 0)
            fps_str = strm.get("r_frame_rate", "0/0")
            if "/" in fps_str:
                n, d = fps_str.split("/")
                fps = int(n) / int(d) if int(d) != 0 else 0.0
            else:
                fps = float(fps_str)
            result["width"] = w
            result["height"] = h
            result["fps"] = fps
            result["info_txt"] = f"{w}x{h} ({fps:.2f}fps)" if w and h else "오디오 파일"

        result["duration"] = duration
        if duration > 0:
            m, s = divmod(int(duration), 60)
            h_val, m = divmod(m, 60)
            result["len_txt"] = (
                f"{h_val:02d}:{m:02d}:{s:02d}" if h_val > 0 else f"{m:02d}:{s:02d}"
            )
    except Exception:
        pass
    return result