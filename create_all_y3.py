#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""create_all_y3.py
PHASE1-B / v02.02.00
Hotfix: normalize editor_lifecycle _save_srt and signal bindings.
"""
from __future__ import annotations

import ast
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_ts = datetime.now().strftime('%Y%m%d_%H%M%S')
BACKUP_DIR = ROOT / f'_backup_y3_{_ts}'
METHOD = 'def _save_srt(self, srt_path, segments):\n    import os\n    from logger import get_logger\n\n    if not segments:\n        get_logger().log(\'❌ 빈 세그먼트라 SRT 저장을 건너뜁니다.\')\n        return\n\n    def _fmt(sec: float) -> str:\n        total_ms = int(round(float(sec) * 1000.0))\n        h = total_ms // 3600000\n        m = (total_ms % 3600000) // 60000\n        s = (total_ms % 60000) // 1000\n        ms = total_ms % 1000\n        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"\n\n    try:\n        out_dir = os.path.dirname(srt_path)\n        if out_dir:\n            os.makedirs(out_dir, exist_ok=True)\n        with open(srt_path, \'w\', encoding=\'utf-8\') as f:\n            for i, seg in enumerate(segments, 1):\n                f.write(f"{i}\\n")\n                f.write(f"{_fmt(seg.get(\'start\', 0.0))} --> {_fmt(seg.get(\'end\', 0.0))}\\n")\n                f.write(f"{str(seg.get(\'text\', \'\') or \'\').strip()}\\n\\n")\n        get_logger().log(f"✅ {os.path.basename(srt_path)} 저장 완료")\n    except Exception as e:\n        get_logger().log(f"❌ SRT 저장 실패: {e}")\n'


def tag(kind, msg):
    print(f'[{kind}] {msg}')


def ensure_backup(path: Path):
    if not path.exists():
        return
    rel = path.relative_to(ROOT)
    dst = BACKUP_DIR / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace('\\r\\n', '\\n'), encoding='utf-8')


def patch_file(path: Path, transform):
    if not path.exists():
        tag('WARN', f'missing: {path.relative_to(ROOT)}')
        return
    old = path.read_text(encoding='utf-8')
    new = transform(old)
    if new == old:
        tag('SKIP', str(path.relative_to(ROOT)))
        return
    if path.suffix.lower() == '.py':
        ast.parse(new)
    ensure_backup(path)
    write_text(path, new)
    tag('OK', str(path.relative_to(ROOT)))


def _remove_method_block(text: str, anchor: str) -> str:
    pos = text.find(anchor)
    if pos == -1:
        return text
    next_def = text.find('\n    def ', pos + 1)
    next_class = text.find('\nclass ', pos + 1)
    candidates = [x for x in (next_def, next_class) if x != -1]
    end = min(candidates) if candidates else len(text)
    return text[:pos] + text[end:]


def patch_editor_lifecycle(text: str) -> str:
    changed = False

    replacements = [
        (
            '        editor.sig_auto_save.connect(lambda segs, p=srt_save_path, ed=editor: self._save_srt_dispatch(ed, p, segs))',
            '        editor.sig_auto_save.connect(lambda segs, p=srt_save_path: self._save_srt(p, segs))',
        ),
        (
            '        editor.sig_save.connect(lambda segs, p=srt_save_path, ed=editor: self._save_srt_dispatch(ed, p, segs))',
            '        editor.sig_save.connect(lambda segs, p=srt_save_path: self._save_srt(p, segs))',
        ),
        (
            '        editor.sig_auto_save.connect(lambda segs, p=srt_save_path, ed=editor: ed._save_srt(p, segs) if hasattr(ed, "_save_srt") else None)',
            '        editor.sig_auto_save.connect(lambda segs, p=srt_save_path: self._save_srt(p, segs))',
        ),
        (
            '        editor.sig_save.connect(lambda segs, p=srt_save_path, ed=editor: ed._save_srt(p, segs) if hasattr(ed, "_save_srt") else None)',
            '        editor.sig_save.connect(lambda segs, p=srt_save_path: self._save_srt(p, segs))',
        ),
    ]
    for old, new in replacements:
        if old in text:
            text = text.replace(old, new, 1)
            changed = True

    helper_anchor = '    def _save_srt_dispatch(self, editor, srt_path, segments):'
    if helper_anchor in text:
        text = _remove_method_block(text, helper_anchor)
        changed = True

    top_anchor = '\ndef _save_srt(self, srt_path, segments):'
    if top_anchor in text:
        start = text.find(top_anchor) + 1
        next_def = text.find('\n    def ', start + 1)
        if next_def == -1:
            next_def = len(text)
        text = text[:start] + text[next_def:]
        changed = True

    class_anchor = '    def _save_srt(self, srt_path, segments):'
    if class_anchor in text:
        text = _remove_method_block(text, class_anchor)
        changed = True

    insert_anchor = '    def _restore_workspace(self, editor, project_path):'
    if insert_anchor in text:
        text = text.replace(insert_anchor, METHOD + '\n' + insert_anchor, 1)
        changed = True
    else:
        text = text.rstrip() + '\n\n' + METHOD + '\n'
        changed = True

    return text if changed else text


def main():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    patch_file(ROOT / 'ui' / 'editor' / 'editor_lifecycle.py', patch_editor_lifecycle)
    tag('OK', f'backup: {BACKUP_DIR.name}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
