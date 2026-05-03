# Version: 02.03.00
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

from core.runtime import config
from core.runtime.logger import get_logger


def render_subtitle_mov(srt_path: str, target_file: str, export_settings: dict,
                        current_idx: int = 1, total_cnt: int = 1) -> bool:
    """투명 자막 영상(MOV) 렌더링 + iCloud 복사"""
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