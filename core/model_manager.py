# Version: 01.00.00
"""
core/model_manager.py
AI 모델 설치/삭제/검증/OS필터 관리
"""
import os
import json
import subprocess
import sys
import importlib

import config
from logger import get_logger

REGISTRY_PATH = os.path.join(config.DATASET_DIR, "model_registry.json")
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_registry() -> list:
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("models", [])
    except Exception:
        return []


def _save_registry(models: list):
    os.makedirs(os.path.dirname(REGISTRY_PATH), exist_ok=True)
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump({"models": models}, f, ensure_ascii=False, indent=2)


def get_current_os() -> str:
    if config.IS_MAC:
        return "mac"
    return "windows"


def get_available_models(include_hidden=False) -> list:
    """현재 OS에서 사용 가능한 모델 목록 반환"""
    models = _load_registry()
    current_os = get_current_os()
    result = []
    for m in models:
        if current_os not in m.get("os", []):
            continue
        if not include_hidden and m.get("hidden", False):
            continue
        m["installed"] = check_installed(m)
        result.append(m)
    return result


def get_required_models() -> list:
    """현재 OS에서 필수인데 미설치된 모델 목록"""
    models = get_available_models()
    return [m for m in models if m.get("required") and not m.get("installed")]


def check_installed(model: dict) -> bool:
    """모델이 설치되어 있는지 확인"""
    # 1) pip 패키지 체크
    for pkg in model.get("pip_packages", []):
        pkg_import = pkg.replace("-", "_").replace(".", "_")
        try:
            importlib.import_module(pkg_import)
        except ImportError:
            return False

    # 2) 로컬 모델 파일 체크 (model_path가 있으면)
    model_path = model.get("model_path", "")
    if model_path:
        full_path = os.path.join(_PROJECT_ROOT, model_path)
        if not os.path.exists(full_path):
            return False
        # model.bin 또는 주요 파일 존재 확인
        has_model_file = any(
            os.path.exists(os.path.join(full_path, f))
            for f in ["model.bin", "config.json", "pytorch_model.bin"]
        )
        if not has_model_file:
            return False

    return True


def install_model(model: dict, progress_callback=None) -> bool:
    """
    모델 설치 (pip 패키지 + 모델 파일)
    progress_callback(status_text, percent) 호출
    """
    model_id = model.get("id", "unknown")
    get_logger().log(f"📦 모델 설치 시작: {model.get('name', model_id)}")

    # 1) pip 패키지 설치
    pip_pkgs = model.get("pip_packages", [])
    for i, pkg in enumerate(pip_pkgs):
        if progress_callback:
            pct = int((i / max(len(pip_pkgs), 1)) * 50)
            progress_callback(f"pip install {pkg}...", pct)

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", pkg],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode != 0:
                get_logger().log(f"  ❌ pip install {pkg} 실패: {result.stderr[:200]}")
                return False
            get_logger().log(f"  ✅ pip install {pkg} 완료")
        except subprocess.TimeoutExpired:
            get_logger().log(f"  ❌ pip install {pkg} 타임아웃")
            return False
        except Exception as e:
            get_logger().log(f"  ❌ pip install {pkg} 오류: {e}")
            return False

    # 2) HuggingFace 모델 다운로드 (model_path가 있으면)
    model_path = model.get("model_path", "")
    if model_path:
        full_path = os.path.join(_PROJECT_ROOT, model_path)
        if not os.path.exists(full_path) or not any(
            os.path.exists(os.path.join(full_path, f))
            for f in ["model.bin", "config.json"]
        ):
            if progress_callback:
                progress_callback("모델 파일 다운로드 중...", 60)

            hf_repo = _model_id_to_hf_repo(model_id)
            if hf_repo:
                try:
                    from huggingface_hub import snapshot_download
                    os.makedirs(full_path, exist_ok=True)
                    snapshot_download(hf_repo, local_dir=full_path)
                    get_logger().log(f"  ✅ 모델 다운로드 완료: {full_path}")
                except Exception as e:
                    get_logger().log(f"  ❌ 모델 다운로드 실패: {e}")
                    get_logger().log(f"  💡 수동 다운로드: https://huggingface.co/{hf_repo}")
                    return False

    if progress_callback:
        progress_callback("설치 완료", 100)

    get_logger().log(f"✅ 모델 설치 완료: {model.get('name', model_id)}")
    return True


def uninstall_model(model: dict) -> bool:
    """모델 삭제 (pip 패키지 제거 + 로컬 파일 삭제)"""
    import shutil
    model_id = model.get("id", "unknown")

    # pip 패키지 제거
    for pkg in model.get("pip_packages", []):
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "uninstall", pkg, "-y"],
                capture_output=True, text=True, timeout=60
            )
            get_logger().log(f"  🗑️ pip uninstall {pkg}")
        except Exception:
            pass

    # 로컬 모델 파일 삭제
    model_path = model.get("model_path", "")
    if model_path:
        full_path = os.path.join(_PROJECT_ROOT, model_path)
        if os.path.exists(full_path):
            shutil.rmtree(full_path, ignore_errors=True)
            get_logger().log(f"  🗑️ 모델 폴더 삭제: {full_path}")

    get_logger().log(f"✅ 모델 삭제 완료: {model.get('name', model_id)}")
    return True


def hide_model(model_id: str):
    """설치 불가 모델 영구 숨김"""
    models = _load_registry()
    for m in models:
        if m["id"] == model_id:
            m["hidden"] = True
            break
    _save_registry(models)


def _model_id_to_hf_repo(model_id: str) -> str:
    """모델 ID → HuggingFace repo 매핑"""
    mapping = {
        "whisper-large-v3-faster": "Systran/faster-whisper-large-v3",
        "whisper-medium-faster": "Systran/faster-whisper-medium",
        "whisper-large-v3-mlx": "mlx-community/whisper-large-v3-mlx",
        "whisper-medium-mlx": "mlx-community/whisper-medium-mlx",
    }
    return mapping.get(model_id, "")


def get_install_summary() -> dict:
    """user_settings 저장용 설치 요약"""
    models = get_available_models(include_hidden=True)
    installed = {}
    pip_list = set()
    for m in models:
        if m.get("installed"):
            installed[m["id"]] = {"name": m["name"], "category": m["category"]}
            for pkg in m.get("pip_packages", []):
                pip_list.add(pkg)
    return {
        "installed_models": installed,
        "installed_pip_packages": sorted(list(pip_list))
    }