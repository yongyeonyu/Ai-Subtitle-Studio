# Version: 02.03.00
# Phase: PHASE1-B
"""
core/model_manager.py
AI 모델 설치/삭제/검증/OS필터 관리
"""
import os
import json
import subprocess
import sys
import importlib
import shutil

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

def _iter_ollama_bins() -> list:
    candidates = [
        shutil.which("ollama"),
        shutil.which("ollama.exe"),

        # macOS
        "/opt/homebrew/bin/ollama",
        "/usr/local/bin/ollama",
        os.path.expanduser("~/.ollama/bin/ollama"),

        # Windows
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
        os.path.expandvars(r"%ProgramFiles%\Ollama\ollama.exe"),
    ]

    result = []
    for path in candidates:
        if path and path not in result and os.path.exists(path):
            result.append(path)
    return result

def _merge_local_llm_models(dst: dict, items: list):
    for m in items:
        name = (m.get("name") or "").strip()
        if not name:
            continue

        size = int(m.get("size", 0) or 0)
        details = dict(m.get("details", {}) or {})

        if name not in dst:
            dst[name] = {
                "name": name,
                "size": size,
                "details": details,
            }
            continue

        prev = dst[name]
        if int(prev.get("size", 0) or 0) <= 0 and size > 0:
            prev["size"] = size
        if not prev.get("details") and details:
            prev["details"] = details

def _scan_ollama_manifest_models() -> list:
    manifest_roots = [
        # macOS / Linux
        os.path.expanduser("~/.ollama/models/manifests"),
        os.path.expanduser("~/Library/Application Support/Ollama/models/manifests"),

        # Windows
        os.path.expandvars(r"%USERPROFILE%\.ollama\models\manifests"),
    ]

    found = {}
    for root in manifest_roots:
        if not root or not os.path.isdir(root):
            continue

        for cur_root, _, files in os.walk(root):
            for fname in files:
                full_path = os.path.join(cur_root, fname)
                rel_parts = [p for p in os.path.relpath(full_path, root).split(os.sep) if p]

                if len(rel_parts) >= 4:
                    namespace = rel_parts[1]
                    model = rel_parts[2]
                    tag = rel_parts[3]
                    if namespace == "library":
                        name = f"{model}:{tag}"
                    else:
                        name = f"{namespace}/{model}:{tag}"
                elif len(rel_parts) >= 2:
                    model = rel_parts[-2]
                    tag = rel_parts[-1]
                    name = f"{model}:{tag}"
                else:
                    continue

                found[name] = {
                    "name": name,
                    "size": 0,
                    "details": {
                        "family": "Ollama Local",
                        "parameter_size": "Local",
                        "format": "ollama",
                    },
                }

    return sorted(found.values(), key=lambda x: x["name"].lower())

def _fetch_local_llm_models_from_cli() -> list:
    for ollama_bin in _iter_ollama_bins():
        try:
            result = subprocess.run(
                [ollama_bin, "list"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=0.8
            )
            if result.returncode != 0 or not result.stdout.strip():
                continue

            found = {}
            for raw in result.stdout.splitlines():
                line = raw.strip()
                if not line or line.upper().startswith("NAME"):
                    continue

                parts = line.split()
                if not parts:
                    continue

                name = parts[0].strip()
                if not name:
                    continue

                found[name] = {
                    "name": name,
                    "size": 0,
                    "details": {
                        "family": "Ollama Local",
                        "parameter_size": "Local",
                        "format": "ollama",
                    },
                }

            if found:
                return sorted(found.values(), key=lambda x: x["name"].lower())

        except Exception:
            pass

    return []

def _fetch_local_llm_models_from_api() -> list:
    try:
        import requests
    except Exception:
        return []

    for url in ("http://127.0.0.1:11434/api/tags", "http://localhost:11434/api/tags"):
        try:
            r = requests.get(url, timeout=0.6)
            if r.status_code != 200:
                continue

            models = []
            for m in r.json().get("models", []):
                name = (m.get("name") or "").strip()
                if not name:
                    continue

                models.append({
                    "name": name,
                    "size": int(m.get("size", 0) or 0),
                    "details": dict(m.get("details", {}) or {}),
                })

            if models:
                return sorted(models, key=lambda x: x["name"].lower())

        except Exception:
            pass

    return []

def get_local_llm_models() -> list:
    merged = {}

    # 1) 설치 파일 스캔 (앱 실행 시 Ollama 서버가 안 떠 있어도 잡힘)
    _merge_local_llm_models(merged, _scan_ollama_manifest_models())

    # 2) CLI 보강
    _merge_local_llm_models(merged, _fetch_local_llm_models_from_cli())

    # 3) API 보강 (size/details 채우기)
    _merge_local_llm_models(merged, _fetch_local_llm_models_from_api())

    if merged:
        return sorted(merged.values(), key=lambda x: x["name"].lower())

    fallback = (getattr(config, "OLLAMA_MODEL", "") or "").strip()
    if fallback:
        return [{
            "name": fallback,
            "size": 0,
            "details": {
                "family": "Default",
                "parameter_size": "Unknown",
                "format": "ollama",
            },
        }]
    return []

OLLAMA_RECOMMENDED_MODELS = [
    {"name": "gemma3:4b", "label": "Gemma3 4B - 무료/로컬 추천", "note": "16GB Mac 기본 자막 교정 균형"},
    {"name": "qwen3:4b", "label": "Qwen3 4B - 무료/로컬 추론", "note": "한국어/추론 균형"},
    {"name": "llama3.2:3b", "label": "Llama3.2 3B - 무료/로컬 빠름", "note": "빠른 대량 교정"},
    {"name": "qwen2.5:7b", "label": "Qwen2.5 7B - 무료/로컬 품질", "note": "긴 문장 교정"},
    {"name": "mistral:7b", "label": "Mistral 7B - 무료/로컬 범용", "note": "범용 보조"},
    {"name": "phi4-mini:latest", "label": "Phi4 Mini - 무료/로컬 경량", "note": "가벼운 교정"},
    {"name": "deepseek-r1:7b", "label": "DeepSeek R1 7B - 무료/로컬 사고", "note": "러프컷 판단 실험"},
    {"name": "gemma3:12b", "label": "Gemma3 12B - 무료/로컬 고품질", "note": "16GB에서 느릴 수 있음"},
]


def is_ollama_available() -> bool:
    return bool(_iter_ollama_bins())


def _run_ollama(args: list[str], timeout: int = 3600) -> tuple[bool, str]:
    bins = _iter_ollama_bins()
    if not bins:
        return False, "Ollama 실행 파일을 찾을 수 없습니다."
    try:
        result = subprocess.run([bins[0], *args], capture_output=True, text=True, encoding="utf-8", timeout=timeout)
        out = (result.stdout or "") + (result.stderr or "")
        return result.returncode == 0, out.strip()
    except Exception as e:
        return False, str(e)


def get_ollama_catalog_models() -> list[dict]:
    installed = {m.get("name") for m in get_local_llm_models()}
    rows = []
    for item in OLLAMA_RECOMMENDED_MODELS:
        row = dict(item)
        row["installed"] = row["name"] in installed
        rows.append(row)
    return rows


def install_ollama_model(model_name: str) -> bool:
    model_name = (model_name or "").strip()
    if not model_name:
        return False
    get_logger().log(f"📦 Ollama 모델 설치 시작: {model_name}")
    ok, out = _run_ollama(["pull", model_name], timeout=7200)
    if ok:
        get_logger().log(f"✅ Ollama 모델 설치 완료: {model_name}")
    else:
        get_logger().log(f"❌ Ollama 모델 설치 실패: {model_name} / {out[:300]}")
    return ok


def uninstall_ollama_model(model_name: str) -> bool:
    model_name = (model_name or "").strip()
    if not model_name:
        return False
    get_logger().log(f"🗑️ Ollama 모델 삭제 시작: {model_name}")
    ok, out = _run_ollama(["rm", model_name], timeout=300)
    if ok:
        get_logger().log(f"✅ Ollama 모델 삭제 완료: {model_name}")
    else:
        get_logger().log(f"❌ Ollama 모델 삭제 실패: {model_name} / {out[:300]}")
    return ok
