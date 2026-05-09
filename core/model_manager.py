# Version: 03.01.23
# Phase: PHASE2
"""
core/model_manager.py
AI 모델 설치/삭제/검증/OS필터 관리
"""
import os
import json
import subprocess
import sys
import importlib.util
import shutil
from copy import deepcopy
from pathlib import Path

from core.runtime import config
from core.llm.secure_keys import get_api_key
from core.runtime.logger import get_logger

REGISTRY_PATH = Path(config.DATASET_DIR) / "model_registry.json"
_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _derive_import_name(pkg: str) -> str:
    return (pkg or "").replace("-", "_").replace(".", "_").strip()


def _resolve_project_path(project_root: Path, raw_path: str) -> Path:
    path = Path(os.path.expandvars(os.path.expanduser(raw_path)))
    if not path.is_absolute():
        path = project_root / path
    return path


class ModelManager:
    """Registry-backed AI model install/delete/status manager."""

    def __init__(
        self,
        registry_path: str | os.PathLike | None = None,
        project_root: str | os.PathLike | None = None,
        current_os: str | None = None,
    ):
        self.registry_path = Path(registry_path) if registry_path else REGISTRY_PATH
        self.project_root = Path(project_root) if project_root else _PROJECT_ROOT
        self.current_os = (current_os or get_current_os()).lower()

    def load_registry(self) -> list[dict]:
        try:
            with self.registry_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return [self._normalize_model(row) for row in data.get("models", [])]
        except Exception as e:
            get_logger().log(f"⚠️ 모델 레지스트리 로드 실패: {e}")
            return []

    def save_registry(self, models: list[dict]):
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        with self.registry_path.open("w", encoding="utf-8") as f:
            json.dump({"models": models}, f, ensure_ascii=False, indent=2)

    def available_models(self, include_hidden=False, include_runtime_discovered=False) -> list[dict]:
        result = []
        seen_ids: set[str] = set()
        for model in self.load_registry():
            supported_os = [str(v).lower() for v in model.get("os", [])]
            if supported_os and self.current_os not in supported_os:
                continue
            if not include_hidden and model.get("hidden", False):
                continue
            row = deepcopy(model)
            row["installed"] = self.check_installed(row)
            result.append(row)
            seen_ids.add(str(row.get("id") or ""))
        if include_runtime_discovered:
            for row in self._discovered_runtime_models():
                row_id = str(row.get("id") or "")
                if row_id and row_id in seen_ids:
                    continue
                result.append(row)
                if row_id:
                    seen_ids.add(row_id)
        return result

    def required_models(self) -> list[dict]:
        return [
            model for model in self.available_models()
            if model.get("required") and not model.get("installed")
        ]

    def check_installed(self, model: dict) -> bool:
        if model.get("binary_check") == "ollama_model":
            target_name = str(model.get("ollama_model_name") or model.get("name") or "").strip()
            if not target_name:
                return False
            return any(str(item.get("name") or "").strip() == target_name for item in get_local_llm_models())
        if model.get("binary_check") == "ollama" or model.get("id") == "ollama":
            return is_ollama_available()
        if model.get("binary_check") == "rnnoise":
            from core.platform_compat import rnnoise_binary

            binary = rnnoise_binary()
            return Path(binary).exists() or shutil.which(binary) is not None

        import_names = model.get("import_names")
        if import_names is None:
            import_names = [_derive_import_name(pkg) for pkg in model.get("pip_packages", [])]
        for import_name in import_names:
            import_name = (import_name or "").strip()
            try:
                if import_name and importlib.util.find_spec(import_name) is None:
                    return False
            except (ImportError, ValueError):
                return False

        model_path = (model.get("model_path") or "").strip()
        if model_path:
            full_path = _resolve_project_path(self.project_root, model_path)
            if not full_path.exists():
                return False
            model_files = model.get("model_files") or [
                "model.bin", "config.json", "pytorch_model.bin", "model.safetensors"
            ]
            if not any((full_path / f).exists() for f in model_files):
                return False

        return True

    def install_model(self, model: dict, progress_callback=None) -> bool:
        model_id = model.get("id", "unknown")
        get_logger().log(f"📦 모델 설치 시작: {model.get('name', model_id)}")

        if model.get("binary_check") == "ollama_model":
            model_name = str(model.get("ollama_model_name") or model.get("name") or "").strip()
            return install_ollama_model(model_name)
        if model.get("binary_check") == "ollama" or model.get("id") == "ollama":
            get_logger().log("💡 Ollama는 외부 앱 설치가 필요합니다: https://ollama.com/download")
            return is_ollama_available()

        pip_pkgs = model.get("pip_packages", [])
        for i, pkg in enumerate(pip_pkgs):
            if progress_callback:
                pct = int((i / max(len(pip_pkgs), 1)) * 50)
                progress_callback(f"pip install {pkg}...", pct)

            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", pkg],
                    capture_output=True, text=True, encoding="utf-8", timeout=300
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

        model_path = (model.get("model_path") or "").strip()
        if model_path:
            full_path = _resolve_project_path(self.project_root, model_path)
            model_files = model.get("model_files") or ["model.bin", "config.json"]
            needs_download = not full_path.exists() or not any((full_path / f).exists() for f in model_files)
            if needs_download:
                if progress_callback:
                    progress_callback("모델 파일 다운로드 중...", 60)
                hf_repo = model.get("hf_repo") or _model_id_to_hf_repo(model_id)
                if hf_repo:
                    try:
                        from huggingface_hub import snapshot_download
                        full_path.mkdir(parents=True, exist_ok=True)
                        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN") or get_api_key("huggingface")
                        snapshot_download(hf_repo, local_dir=str(full_path), token=token or None)
                        get_logger().log(f"  ✅ 모델 다운로드 완료: {full_path}")
                    except Exception as e:
                        get_logger().log(f"  ❌ 모델 다운로드 실패: {e}")
                        get_logger().log(f"  💡 수동 다운로드: https://huggingface.co/{hf_repo}")
                        return False

        if progress_callback:
            progress_callback("설치 완료", 100)

        get_logger().log(f"✅ 모델 설치 완료: {model.get('name', model_id)}")
        return True

    def uninstall_model(self, model: dict) -> bool:
        model_id = model.get("id", "unknown")

        if model.get("binary_check") == "ollama_model":
            model_name = str(model.get("ollama_model_name") or model.get("name") or "").strip()
            return uninstall_ollama_model(model_name)
        if model.get("binary_check") == "ollama" or model.get("id") == "ollama":
            get_logger().log("💡 Ollama 앱 삭제는 운영체제 앱 관리에서 진행하세요.")
            return True

        for pkg in model.get("pip_packages", []):
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "uninstall", pkg, "-y"],
                    capture_output=True, text=True, encoding="utf-8", timeout=60
                )
                get_logger().log(f"  🗑️ pip uninstall {pkg}")
            except Exception as e:
                get_logger().log(f"  ⚠️ pip uninstall {pkg} 실패: {e}")

        model_path = (model.get("model_path") or "").strip()
        if model_path:
            full_path = _resolve_project_path(self.project_root, model_path)
            if full_path.exists():
                shutil.rmtree(full_path, ignore_errors=True)
                get_logger().log(f"  🗑️ 모델 폴더 삭제: {full_path}")

        get_logger().log(f"✅ 모델 삭제 완료: {model.get('name', model_id)}")
        return True

    def hide_model(self, model_id: str):
        models = self.load_registry()
        for model in models:
            if model.get("id") == model_id:
                model["hidden"] = True
                break
        self.save_registry(models)

    def install_summary(self) -> dict:
        models = self.available_models(include_hidden=True)
        installed = {}
        pip_list = set()
        for model in models:
            if model.get("installed"):
                installed[model["id"]] = {
                    "name": model["name"],
                    "category": model["category"],
                }
                for pkg in model.get("pip_packages", []):
                    pip_list.add(pkg)
        return {
            "installed_models": installed,
            "installed_pip_packages": sorted(pip_list),
        }

    def _normalize_model(self, model: dict) -> dict:
        row = dict(model or {})
        row.setdefault("id", "")
        row.setdefault("name", row.get("id", "unknown"))
        row.setdefault("category", "Other")
        row.setdefault("os", ["mac", "windows"])
        row.setdefault("pip_packages", [])
        row.setdefault("model_path", "")
        row.setdefault("required", False)
        row.setdefault("hidden", False)
        if row.get("import_names") is None and row.get("pip_packages"):
            row["import_names"] = [_derive_import_name(pkg) for pkg in row.get("pip_packages", [])]
        return row

    def _discovered_runtime_models(self) -> list[dict]:
        discovered: list[dict] = []
        for item in get_local_llm_models():
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            details = dict(item.get("details", {}) or {})
            discovered.append(
                {
                    "id": f"ollama-model::{name}",
                    "name": name,
                    "category": "LLM",
                    "os": [self.current_os],
                    "pip_packages": [],
                    "model_path": "",
                    "required": False,
                    "hidden": False,
                    "installed": True,
                    "binary_check": "ollama_model",
                    "ollama_model_name": name,
                    "details": details,
                    "discovered": True,
                    "size_bytes": int(item.get("size", 0) or 0),
                }
            )
        return discovered


def _load_registry() -> list:
    return ModelManager().load_registry()


def _save_registry(models: list):
    ModelManager().save_registry(models)


def get_current_os() -> str:
    if config.IS_MAC:
        return "mac"
    if getattr(config, "IS_WINDOWS", False):
        return "windows"
    if getattr(config, "IS_LINUX", False):
        return "linux"
    return "windows"


def get_available_models(include_hidden=False, include_runtime_discovered=False) -> list:
    """현재 OS에서 사용 가능한 모델 목록 반환"""
    return ModelManager().available_models(
        include_hidden=include_hidden,
        include_runtime_discovered=include_runtime_discovered,
    )


def get_required_models() -> list:
    """현재 OS에서 필수인데 미설치된 모델 목록"""
    return ModelManager().required_models()


def check_installed(model: dict) -> bool:
    """모델이 설치되어 있는지 확인"""
    return ModelManager().check_installed(model)


def install_model(model: dict, progress_callback=None) -> bool:
    """
    모델 설치 (pip 패키지 + 모델 파일)
    progress_callback(status_text, percent) 호출
    """
    return ModelManager().install_model(model, progress_callback=progress_callback)


def uninstall_model(model: dict) -> bool:
    """모델 삭제 (pip 패키지 제거 + 로컬 파일 삭제)"""
    return ModelManager().uninstall_model(model)


def hide_model(model_id: str):
    """설치 불가 모델 영구 숨김"""
    ModelManager().hide_model(model_id)


def _model_id_to_hf_repo(model_id: str) -> str:
    """모델 ID → HuggingFace repo 매핑"""
    mapping = {
        "whisper-large-v3-faster": "Systran/faster-whisper-large-v3",
        "whisper-medium-faster": "Systran/faster-whisper-medium",
        "whisper-large-v3-mlx": "mlx-community/whisper-large-v3-mlx",
        "whisper-medium-mlx": "mlx-community/whisper-medium-mlx",
        "whisper-korean-ghost613-mlx": "youngouk/ghost613-turbo-korean-4bit-mlx",
        "whisper-korean-ghost613-faster": "ghost613/faster-whisper-large-v3-turbo-korean",
    }
    return mapping.get(model_id, "")


def get_install_summary() -> dict:
    """user_settings 저장용 설치 요약"""
    return ModelManager().install_summary()

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
