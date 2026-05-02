from pathlib import Path
from datetime import datetime
import shutil
import os

cmd_path = Path("/Users/u_mo_c/Downloads/ai_subtitle_studio.command")
project_dir = Path("/Users/u_mo_c/Downloads/ai_subtitle_studio")
venv_python = project_dir / "venv" / "bin" / "python3.11"

if not cmd_path.exists():
    print("❌ .command 파일을 찾을 수 없습니다:", cmd_path)
    raise SystemExit(1)

if not venv_python.exists():
    print("❌ venv Python을 찾을 수 없습니다:", venv_python)
    raise SystemExit(1)

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
bak = cmd_path.with_suffix(cmd_path.suffix + f".bak_{stamp}")
shutil.copy2(cmd_path, bak)
print("📦 백업 완료:", bak)

new_content = f'''#!/bin/bash
cd "{project_dir}" || exit 1

export PYTHONPATH="$PYTHONPATH:."

# 반드시 프로젝트 venv Python으로 실행한다.
# 시스템 python3.11로 실행하면 cv2/opencv-python 등 venv 패키지를 못 찾을 수 있다.
"{venv_python}" main.py
'''

cmd_path.write_text(new_content, encoding="utf-8")
os.chmod(cmd_path, 0o755)

print("✅ ai_subtitle_studio.command를 venv Python 실행 방식으로 수정 완료")
print()
print("수정된 내용:")
print(cmd_path.read_text(encoding="utf-8"))
