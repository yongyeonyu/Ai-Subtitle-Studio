from __future__ import annotations

import hashlib
import os
from functools import lru_cache
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


@lru_cache(maxsize=512)
def _sample_digest_for_stat(
    abs_path: str,
    size: int,
    mtime_ns: int,
    ctime_ns: int,
    inode: int,
    device: int,
    sample_bytes: int,
) -> str:
    _ = (mtime_ns, ctime_ns, inode, device)
    digest = hashlib.sha1()
    sample_size = max(1, int(sample_bytes))
    try:
        with open(abs_path, "rb") as handle:
            digest.update(handle.read(sample_size))
            if size > sample_size:
                handle.seek(max(0, size - sample_size))
                digest.update(handle.read(sample_size))
        return digest.hexdigest()
    except OSError:
        return ""


def media_file_fingerprint(path: str, *, sample_bytes: int = 1024 * 1024, include_samples: bool = True) -> str:
    """Return a cache-safe media signature that survives same-name file replacement."""
    abs_path = os.path.abspath(os.path.expanduser(str(path or "")))
    try:
        stat = os.stat(abs_path)
    except OSError:
        return abs_path

    size = int(getattr(stat, "st_size", 0) or 0)
    mtime_ns = _stat_ns(stat, "st_mtime_ns", "st_mtime")
    ctime_ns = _stat_ns(stat, "st_ctime_ns", "st_ctime")
    inode = int(getattr(stat, "st_ino", 0) or 0)
    device = int(getattr(stat, "st_dev", 0) or 0)

    parts = [
        abs_path,
        str(size),
        str(mtime_ns),
        str(ctime_ns),
        str(inode),
        str(device),
    ]
    if include_samples and size > 0 and sample_bytes > 0:
        sample_digest = _sample_digest_for_stat(
            abs_path,
            size,
            mtime_ns,
            ctime_ns,
            inode,
            device,
            int(sample_bytes),
        )
        if sample_digest:
            parts.append(sample_digest)
    return "|".join(parts)


def media_fingerprint_digest(path: str, *, sample_bytes: int = 1024 * 1024, include_samples: bool = True) -> str:
    signature = media_file_fingerprint(path, sample_bytes=sample_bytes, include_samples=include_samples)
    return hashlib.sha1(signature.encode("utf-8", errors="ignore")).hexdigest()


__all__ = ["media_file_fingerprint", "media_fingerprint_digest"]
