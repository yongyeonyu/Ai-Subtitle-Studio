from pathlib import Path

from tools.verify_reference_fixture_availability import build_availability_report


def _write_srt(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "1",
                "00:00:00,000 --> 00:00:01,000",
                "hello",
                "",
                "2",
                "00:00:02,000 --> 00:00:03,000",
                "world",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_reference_fixture_availability_reports_ready_when_media_and_reference_exist(tmp_path):
    media = tmp_path / "clip.mp4"
    reference = tmp_path / "clip.srt"
    media.write_bytes(b"media")
    _write_srt(reference)

    report = build_availability_report(media=media, reference_srt=reference, start_sec=0.0, duration_sec=3.0)

    assert report["ready_for_reference_scored_benchmark"] is True
    assert report["blocking_reasons"] == []
    assert report["reference_srt"]["segment_count"] == 2
    assert report["reference_srt"]["clipped_segment_count"] == 2
    assert "--reference-srt" in report["benchmark_command"]


def test_reference_fixture_availability_blocks_when_reference_is_missing_but_fallback_exists(tmp_path):
    media = tmp_path / "clip.mp4"
    fallback = tmp_path / "cached.wav"
    media.write_bytes(b"media")
    fallback.write_bytes(b"audio")

    report = build_availability_report(
        media=media,
        reference_srt=tmp_path / "missing.srt",
        fallback_media=[fallback],
        start_sec=0.0,
        duration_sec=180.0,
    )

    assert report["ready_for_reference_scored_benchmark"] is False
    assert report["blocking_reasons"] == ["reference_srt_missing"]
    assert report["non_reference_media_available"] is True
    assert "must not approve latency trims" in report["non_reference_warning"]
    assert report["benchmark_command"] == ""


def test_reference_fixture_availability_blocks_when_media_and_reference_are_missing(tmp_path):
    fallback = tmp_path / "cached.wav"
    fallback.write_bytes(b"audio")

    report = build_availability_report(
        media=tmp_path / "missing.mp4",
        reference_srt=tmp_path / "missing.srt",
        fallback_media=[fallback],
        start_sec=0.0,
        duration_sec=180.0,
    )

    assert report["ready_for_reference_scored_benchmark"] is False
    assert report["blocking_reasons"] == ["reference_media_missing", "reference_srt_missing"]
    assert report["media"]["is_file"] is False
    assert report["reference_srt"]["is_file"] is False
    assert report["non_reference_media_available"] is True
    assert report["benchmark_command"] == ""
