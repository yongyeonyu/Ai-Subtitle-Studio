# Version: 02.03.00
# Phase: PHASE1-B
"""
core/llm/secure_keys.py
OS 보안 저장소 기반 API Key 저장/조회 유틸.
macOS는 Keychain security CLI를 우선 사용하고, Windows/Linux는 keyring 패키지가 있으면 사용합니다.
"""
from __future__ import annotations

import platform
import subprocess


SERVICE = "AI Subtitle Studio"
_PROVIDERS = {"google", "openai"}


def _account(provider: str) -> str:
    provider = (provider or "").strip().lower()
    if provider not in _PROVIDERS:
        raise ValueError(f"unsupported provider: {provider}")
    return f"{provider}_api_key"


def _keyring_module():
    try:
        import keyring  # type: ignore
        return keyring
    except Exception:
        return None


def _mac_get(account: str) -> str:
    try:
        cp = subprocess.run(
            ["security", "find-generic-password", "-a", account, "-s", SERVICE, "-w"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        return cp.stdout.strip() if cp.returncode == 0 else ""
    except Exception:
        return ""


def _mac_set(account: str, value: str) -> bool:
    try:
        subprocess.run(
            ["security", "delete-generic-password", "-a", account, "-s", SERVICE],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        cp = subprocess.run(
            ["security", "add-generic-password", "-a", account, "-s", SERVICE, "-w", value, "-U"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return cp.returncode == 0
    except Exception:
        return False


def _mac_delete(account: str) -> bool:
    try:
        cp = subprocess.run(
            ["security", "delete-generic-password", "-a", account, "-s", SERVICE],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        return cp.returncode == 0
    except Exception:
        return False


def get_api_key(provider: str) -> str:
    account = _account(provider)
    kr = _keyring_module()
    if kr is not None:
        try:
            value = kr.get_password(SERVICE, account) or ""
            if value:
                return value
        except Exception:
            pass
    if platform.system() == "Darwin":
        return _mac_get(account)
    return ""


def set_api_key(provider: str, value: str) -> bool:
    account = _account(provider)
    value = (value or "").strip()
    if not value:
        return delete_api_key(provider)
    kr = _keyring_module()
    if kr is not None:
        try:
            kr.set_password(SERVICE, account, value)
            return True
        except Exception:
            pass
    if platform.system() == "Darwin":
        return _mac_set(account, value)
    return False


def delete_api_key(provider: str) -> bool:
    account = _account(provider)
    ok = False
    kr = _keyring_module()
    if kr is not None:
        try:
            kr.delete_password(SERVICE, account)
            ok = True
        except Exception:
            pass
    if platform.system() == "Darwin":
        ok = _mac_delete(account) or ok
    return ok


def has_api_key(provider: str) -> bool:
    return bool(get_api_key(provider))
