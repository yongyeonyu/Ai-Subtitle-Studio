from pathlib import Path
from unittest.mock import patch

from core import media_info


def test_media_fingerprint_cache_reuses_digest_for_unchanged_file(tmp_path):
    media_path = tmp_path / "sample.mp4"
    media_path.write_bytes(b"video" * 32)

    media_info._FINGERPRINT_CACHE.clear()
    with patch("core.media_info.media_fingerprint_digest", return_value="digest-1") as digest:
        first_key, first_path = media_info._fingerprint(str(media_path))
        second_key, second_path = media_info._fingerprint(str(media_path))

    assert first_key == "digest-1"
    assert second_key == "digest-1"
    assert first_path == second_path
    assert digest.call_count == 1


def test_directory_usage_uses_nested_file_sizes(tmp_path):
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    (tmp_path / "one.bin").write_bytes(b"123")
    (nested / "two.bin").write_bytes(b"12345")

    from core.runtime.memory_manager import _directory_usage

    total_bytes, file_count = _directory_usage(Path(tmp_path))
    assert total_bytes == 8
    assert file_count == 2
