# Version: 03.14.07
# Phase: PHASE1-B
"""
core/renderer.py
투명 자막 영상(MOV) 렌더링 + iCloud 복사
- backend.py에서 분리
"""

import os
import subprocess
import tempfile
import shutil
import re
import json

from core.runtime import config
from core.runtime.logger import get_logger


_RENDER_QT_APP = None


def _ensure_qt_application_for_rendering() -> object | None:
    """Create a minimal QApplication when renderer helpers run standalone."""
    global _RENDER_QT_APP
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        return None

    app = QApplication.instance() or _RENDER_QT_APP
    if app is not None:
        _RENDER_QT_APP = app
        return app

    # CLI/manual render helpers can run outside the main app process. Without a
    # QApplication, font/database access aborts the Python process on macOS.
    try:
        app = QApplication([])
    except Exception:
        return None
    _RENDER_QT_APP = app

    try:
        from core.runtime.qt_runtime import configure_qt_application_font

        configure_qt_application_font()
    except Exception:
        pass
    return app


def _ffprobe_video_info(path: str) -> dict:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,width,height,bit_rate",
        "-of",
        "json",
        str(path or ""),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        if result.returncode != 0:
            return {}
        payload = json.loads(result.stdout or "{}")
        streams = payload.get("streams") or []
        return dict(streams[0]) if streams else {}
    except Exception:
        return {}


def _video_toolbox_encode_args(video_info: dict, output_path: str) -> list[str]:
    codec = str(video_info.get("codec_name") or "").lower()
    try:
        source_bitrate = int(video_info.get("bit_rate") or 0)
    except Exception:
        source_bitrate = 0
    try:
        width = int(video_info.get("width") or 0)
        height = int(video_info.get("height") or 0)
    except Exception:
        width, height = 0, 0
    fallback_bitrate = 45_000_000 if max(width, height) >= 3000 else 18_000_000
    bitrate = max(8_000_000, source_bitrate or fallback_bitrate)
    encoder = "hevc_videotoolbox" if codec in {"hevc", "h265"} else "h264_videotoolbox"
    args = [
        "-c:v",
        encoder,
        "-b:v",
        str(bitrate),
        "-maxrate",
        str(int(bitrate * 1.5)),
        "-bufsize",
        str(int(bitrate * 2)),
    ]
    if encoder == "h264_videotoolbox":
        args.extend(["-profile:v", "high"])
    if str(output_path or "").lower().endswith(".mp4"):
        args.extend(["-movflags", "+faststart"])
    return args


def _ffmpeg_error_tail(stderr: str, *, limit: int = 1800) -> str:
    text = str(stderr or "").strip()
    if not text:
        return "(stderr 없음)"
    lines = [line for line in text.splitlines() if line.strip()]
    tail = "\n".join(lines[-24:])
    return tail[-limit:]


def render_subtitle_overlay_video_gpu(
    srt_path: str,
    target_file: str,
    export_settings: dict | None = None,
    output_path: str | None = None,
) -> bool:
    """Burn subtitles into the source video using a VideoToolbox GPU encoder."""
    target_file = os.path.abspath(str(target_file or ""))
    srt_path = os.path.abspath(str(srt_path or ""))
    if not target_file or not os.path.exists(target_file):
        get_logger().log("❌ 자막 오버레이 출력 실패: 원본 영상 파일이 없습니다.")
        return False
    if not srt_path or not os.path.exists(srt_path):
        get_logger().log("❌ 자막 오버레이 출력 실패: SRT 파일이 없습니다.")
        return False
    ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
    base = os.path.splitext(os.path.basename(target_file))[0]
    output_path = os.path.abspath(
        str(output_path or os.path.join(os.path.dirname(target_file), f"{base}_자막입힘.mp4"))
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    video_info = _ffprobe_video_info(target_file)
    work_dir = tempfile.mkdtemp(prefix="ai_subtitle_overlay_mov_")
    encode_args = _video_toolbox_encode_args(video_info, output_path)
    get_logger().log(f"🎥 영상+자막 오버레이 출력(GPU) 시작: {os.path.basename(output_path)}")
    try:
        render_settings = dict(export_settings or {})
        render_settings["icloud"] = False
        try:
            source_width = int(video_info.get("width") or 0)
        except Exception:
            source_width = 0
        render_settings["res"] = "4K (3840px)" if source_width >= 3000 else "FHD (1920px)"
        temp_media_ref = os.path.join(work_dir, os.path.basename(target_file))
        if not render_subtitle_mov(srt_path, temp_media_ref, render_settings, 1, 1):
            get_logger().log("❌ 영상+자막 오버레이 출력 실패: 투명 자막 MOV 생성 실패")
            return False
        candidates = sorted(name for name in os.listdir(work_dir) if name.endswith("_자막소스.mov"))
        if not candidates:
            get_logger().log("❌ 영상+자막 오버레이 출력 실패: 투명 자막 MOV 파일이 없습니다.")
            return False
        subtitle_mov = os.path.join(work_dir, candidates[0])
        overlay_filter = "[0:v][1:v]overlay=(main_w-overlay_w)/2:main_h-overlay_h:eof_action=pass:format=auto[v]"

        def _cmd(audio_codec: str) -> list[str]:
            return [
                ffmpeg_bin,
                "-y",
                "-hwaccel",
                "videotoolbox",
                "-i",
                target_file,
                "-i",
                subtitle_mov,
                "-filter_complex",
                overlay_filter,
                "-map",
                "[v]",
                "-map",
                "0:a?",
                *encode_args,
                "-c:a",
                audio_codec,
                output_path,
            ]

        result = subprocess.run(_cmd("copy"), capture_output=True, text=True)
        if result.returncode != 0:
            result = subprocess.run(_cmd("aac"), capture_output=True, text=True)
        if result.returncode != 0:
            get_logger().log(f"❌ 영상+자막 오버레이 출력 실패:\n{_ffmpeg_error_tail(result.stderr)}")
            return False
        if os.path.exists(output_path):
            get_logger().log(f"✅ 영상+자막 오버레이 출력 완료: {os.path.basename(output_path)}")
            return True
        get_logger().log("❌ 영상+자막 오버레이 출력 실패: 출력 파일이 생성되지 않았습니다.")
        return False
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def render_subtitle_mov(srt_path: str, target_file: str, export_settings: dict,
                        current_idx: int = 1, total_cnt: int = 1) -> bool:
    """투명 자막 영상(MOV) 렌더링 + iCloud 복사"""
    _ensure_qt_application_for_rendering()
    from PyQt6.QtGui import QColor, QImage
    from PyQt6.QtCore import Qt

    try:
        from ui.dialogs.export_dialog import _parse_srt, _make_png
    except ImportError:
        from ui.dialogs.export_dialog import _parse_srt, _make_png

    s = export_settings
    segs = _parse_srt(srt_path)
    if not segs:
        return False

    res_text = s.get("res", "4K (3840px)")
    width = 3840 if "4K" in res_text else 1920
    fs = int(s.get("size", 60))
    res_scale = 4.0 if width == 3840 else 2.0
    scaled_fs = int(fs * res_scale)
    height = int(scaled_fs * 3.5)
    height += height % 2

    bg_c = QColor(s.get("bg_c", "#000000"))
    bg_rgba = (
        bg_c.red(), bg_c.green(), bg_c.blue(),
        int(s.get("bg_op", 50) * 2.55)
    ) if s.get("bg", False) else None

    bdr_w = int(s.get("bdr_w", 2))
    bdr_w = max(1, int(bdr_w * res_scale)) if bdr_w > 0 and not s.get("no_bdr", False) else 0

    txt_c = QColor(s.get("txt_c", "#FFFFFF"))
    bdr_c = QColor(s.get("bdr_c", "#FFFFFF"))
    shd_c = QColor(s.get("shd_c", "#000000"))
    try:
        vertical_offset = int(int(s.get("text_height", 0) or 0) * res_scale)
    except Exception:
        vertical_offset = 0

    style = dict(
        font_path="",
        font_family=s.get("font", "Apple SD Gothic Neo"),
        font_size=scaled_fs,
        res_scale=res_scale,
        bold=s.get("bold", True),
        align=s.get("align", "가운데"),
        line_spacing=int(int(s.get("lsp", 6)) * res_scale),
        txt_rgba=(txt_c.red(), txt_c.green(), txt_c.blue(), 255),
        border_w=bdr_w,
        border_rgba=(bdr_c.red(), bdr_c.green(), bdr_c.blue(), 255),
        shadow_rgba=(
            shd_c.red(), shd_c.green(), shd_c.blue(), 200
        ) if s.get("shadow", False) else None,
        shadow_x=int(int(s.get("shdx", 3)) * res_scale),
        shadow_y=int(int(s.get("shdy", 3)) * res_scale),
        vertical_offset=vertical_offset,
        bg_rgba=bg_rgba,
        bg_radius=int(s.get("bg_radius", 10) * res_scale),
        bg_margin=int(s.get("bg_margin", 18) * res_scale),
        bg_full_width=s.get("bg_full", False),
    )

    total_dur = max(seg["end"] for seg in segs) + 0.5
    wd = tempfile.mkdtemp(prefix="sub_exp_auto_")
    safe_v = re.sub(r'[\\/:*?"<>|]', "_", os.path.basename(target_file))
    out_p = os.path.join(
        os.path.dirname(target_file),
        f"{os.path.splitext(safe_v)[0]}_자막소스.mov"
    )

    try:
        pts = sorted(
            {0.0, total_dur}
            | {sg["start"] for sg in segs}
            | {sg["end"] for sg in segs}
        )
        events = []
        for i in range(len(pts) - 1):
            t0, t1 = pts[i], pts[i + 1]
            if t1 - t0 < 0.001:
                continue
            txt = next(
                (sg["text"] for sg in segs if sg["start"] <= t0 and sg["end"] >= t1),
                None,
            )
            events.append((t0, t1, txt))

        blank = os.path.join(wd, "blank.png")
        bg_img = QImage(width, height, QImage.Format.Format_ARGB32)
        bg_img.fill(Qt.GlobalColor.transparent)
        bg_img.save(blank, "PNG")

        txt_png = {}
        unique = {e[2] for e in events if e[2]}
        for i, text in enumerate(unique):
            p2 = os.path.join(wd, f"s{i:04d}.png")
            _make_png(p2, text, width, height, style)
            txt_png[text] = p2

        concat = os.path.join(wd, "c.txt")
        with open(concat, "w", encoding="utf-8") as f:
            for t0, t1, txt in events:
                f.write(
                    f"file '{txt_png.get(txt, blank) if txt else blank}'\n"
                    f"duration {t1 - t0:.6f}\n"
                )
            if events:
                f.write(
                    f"file '{txt_png.get(events[-1][2], blank) if events[-1][2] else blank}'\n"
                )

        enc = ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"]
        if "빠른" in s.get("quality", "빠른"):
            enc.extend(["-q:v", "15"])

        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat, "-vf", "format=yuva444p10le"
        ] + enc + [out_p]

        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            get_logger().log(f"❌ ffmpeg 실패:\n{(r.stderr or '')[:500]}")
            return False

        if os.path.exists(out_p):
            get_logger().log(f"    └ ✅ MOV 렌더링 완료: {os.path.basename(out_p)}")

            if s.get("icloud", False):
                dest_dir = getattr(
                    config, "ICLOUD_DROPZONE",
                    os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT"),
                )
                os.makedirs(dest_dir, exist_ok=True)
                dest_file = os.path.join(dest_dir, os.path.basename(out_p))

                if os.path.abspath(out_p) != os.path.abspath(dest_file):
                    get_logger().log("    └ ☁️ iCloud로 자동 복사 중...")
                    shutil.copy2(out_p, dest_file)
                    get_logger().log("    └ ✅ iCloud 복사 완료")

            return True

    finally:
        shutil.rmtree(wd, ignore_errors=True)

    return False
