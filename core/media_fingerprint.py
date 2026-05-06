from __future__ import annotations

import hashlib
import os
from typing import Any


def _stat_ns(stat: Any, attr: str, fallback_attr: str) -> int:
    value = getattr(stat, attr, None)
    if value is not None:
        try:
            return int(value)
        except Exception:
            pass
    try:
        return int(float(getattr(stat, fallback_attr, 0.0)) * 1_000_000_000)
    except Exception:
        return 0


def media_file_fingerprint(path: str, *, sample_bytes: int = 1024 * 1024, include_samples: bool = True) -> str:
    """Return a cache-safe media signature that survives same-name file replacement."""
    abs_path = os.path.abspath(os.path.expanduser(str(path or "")))
    try:
        stat = os.stat(abs_path)
    except OSError:
        return abs_path

    parts = [
        abs_path,
        str(int(getattr(stat, "st_size", 0) or 0)),
        str(_stat_ns(stat, "st_mtime_ns", "st_mtime")),
        str(_stat_ns(stat, "st_ctime_ns", "st_ctime")),
        str(int(getattr(stat, "st_ino", 0) or 0)),
        str(int(getattr(stat, "st_dev", 0) or 0)),
    ]
    if include_samples and int(getattr(stat, "st_size", 0) or 0) > 0 and sample_bytes > 0:
        digest = hashlib.sha1()
        sample_size = max(1, int(sample_bytes))
        try:
            with open(abs_path, "rb") as handle:
                digest.update(handle.read(sample_size))
                if stat.st_size > sample_size:
                    handle.seek(max(0, stat.st_size - sample_size))
                    digest.update(handle.read(sample_size))
            parts.append(digest.hexdigest())
        except OSError:
            pass
    return "|".join(parts)


def media_fingerprint_digest(path: str, *, sample_bytes: int = 1024 * 1024, include_samples: bool = True) -> str:
    signature = media_file_fingerprint(path, sample_bytes=sample_bytes, include_samples=include_samples)
    return hashlib.sha1(signature.encode("utf-8", errors="ignore")).hexdigest()


__all__ = ["media_file_fingerprint", "media_fingerprint_digest"]
