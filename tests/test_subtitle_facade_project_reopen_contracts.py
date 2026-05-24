import copy
from pathlib import Path

import numpy as np

from core.engine.subtitle_global_canvas import global_canvas_minimap_rows
from core.engine.subtitle_segments import prepare_save_reopen_segments
from core.engine.subtitle_stt_segments import prepare_stt_preview_timeline_rows
from core.engine.subtitle_waveform import build_waveform_columns
from core.pipeline.subtitle_parallel_manager import build_subtitle_parallel_iteration_plan
from core.project.project_assets import (
    externalize_project_text_assets,
    hydrate_project_text_asset_cache,
    load_external_subtitle_segments,
    load_external_stt_tracks,
)


def _reopen_project_payload(project: dict) -> dict:
    reopened = copy.deepcopy(project)
    for key in (
        "_hot_open_subtitle_segments_cache",
        "_external_subtitle_segments_cache",
        "_external_stt_tracks_cache",
    ):
        reopened.pop(key, None)
    return reopened


def test_facade_rows_survive_project_external_srt_reopen_contract(tmp_path: Path):
    project_path = tmp_path / "tinyping_x5_fixture.aissproj"
    project = {
        "_project_file_path": str(project_path),
        "project_path": str(project_path),
        "media": {"items": [{"path": "DJI_20260217224203_0075_D.MP4", "fps": 30.0}]},
        "subtitles": {},
        "editor_state": {
            "subtitles": {},
            "rendering": {"subtitle_canvas": {}},
            "stt": {"candidate_tracks": {}},
            "analysis": {},
        },
        "analysis": {},
    }
    final_source = [
        {
            "start": 0.999,
            "end": 2.001,
            "text": "프로젝트 저장.",
            "timeline_frame_rate": 30.0,
            "speaker": "00",
        },
        {
            "start": 2.001,
            "end": 3.467,
            "text": "다음 줄",
            "timeline_frame_rate": 30.0,
            "speaker": "00",
        },
    ]
    stt1 = prepare_stt_preview_timeline_rows(
        [
            {"start": 0.0, "end": 1.0, "text": "프로젝트 저장", "timeline_frame_rate": 30.0},
            {"start": 1.0, "end": 2.4, "text": "다음 줄", "timeline_frame_rate": 30.0},
        ],
        source_label="stt1",
        clip_offset=0.999,
        clip_idx=0,
        clip_path="DJI_20260217224203_0075_D.MP4",
        optimized=True,
    )

    prepared = prepare_save_reopen_segments(final_source, apply_offset=False)
    externalize_project_text_assets(
        str(project_path),
        project,
        final_segments=prepared.prepared_segments,
        stt_tracks={"STT1": stt1.rows},
    )
    reopened = hydrate_project_text_asset_cache(_reopen_project_payload(project))

    final_rows = load_external_subtitle_segments(reopened)
    stt_tracks = load_external_stt_tracks(reopened)

    assert [(row["text"], round(row["start"], 3), round(row["end"], 3)) for row in final_rows] == [
        ("프로젝트 저장", 1.0, 2.0),
        ("다음 줄", 2.0, 3.467),
    ]
    assert set(stt_tracks) == {"STT1"}
    assert stt_tracks["STT1"][0]["stt_preview_source"] == "STT1"
    assert stt_tracks["STT1"][0]["_clip_idx"] == 0
    assert stt_tracks["STT1"][0]["_clip_file"].endswith("0075_D.MP4")
    assert reopened["editor_state"]["stt"]["candidate_counts"] == {"STT1": 2}

    canvas_rows = global_canvas_minimap_rows(final_rows + stt_tracks["STT1"], lanes=("SUBTITLE", "STT1"))
    assert [row["lane"] for row in canvas_rows] == ["SUBTITLE", "SUBTITLE", "STT1", "STT1"]

    waveform_columns = build_waveform_columns(
        np.array([0.0, 0.25, 0.5, 0.75, 1.0], dtype=np.float32),
        width=5,
        total_duration=5.0,
        vad_segments=final_rows,
        allow_native=False,
    )
    assert len(waveform_columns) == 5
    assert any(in_speech for _height, in_speech in waveform_columns)

    plan = build_subtitle_parallel_iteration_plan(
        target_file="DJI_20260217224203_0075_D.MP4",
        queue_index=0,
        total_files=1,
        cut_boundary_snapshot={"cut_boundaries": [{"timeline_sec": row["start"]} for row in final_rows]},
    )
    assert plan.hard_cut_boundaries == (1.0, 2.0)
    assert plan.stage_dag[-1].stage == "editor_feed"
