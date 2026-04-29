# Version: 03.00.26
# Phase: PHASE2
"""Local rough-cut engine helpers.

Phase2 keeps the analysis pipeline isolated from subtitle generation and
editing. Public functions here are intentionally pure where possible so they
can be tested without loading Qt, ffmpeg, or network services.
"""

from .gap_detector import TimelineGap, detect_subtitle_gaps, merge_close_gaps
from .edit_decision_engine import CutSafetyResult, build_edit_decisions, classify_cut_safety
from .edl_generator import build_edl_segments, edl_to_dict, map_edl_segments_to_clip_sources, save_edl_json
from .guide_writer import build_markdown_guide, save_markdown_guide
from .pipeline import run_roughcut_pipeline
from .renderer_skeleton import (
    RenderCommandPlan,
    build_concat_render_plan,
    build_ffmpeg_concat_command,
    build_ffmpeg_extract_command,
    build_ffmpeg_subtitle_burnin_command,
    ffmpeg_available,
)
from .render_executor import RenderExecutionResult, run_render_plan, write_concat_file
from .subtitle_retimer import format_srt, retime_subtitles_for_edl, save_retimed_srt
from .models import (
    ChapterBoundaryCandidate,
    ChapterMetadata,
    EDLSegment,
    EditDecision,
    PackedPhrase,
    RoughCutResult,
    RoughCutSegment,
    SemanticChunk,
    StoryboardCandidate,
    StoryboardPlan,
    SubtitleSegment,
    TimelineEvent,
    VisualSceneNote,
    subtitle_from_dict,
    subtitles_from_dicts,
    roughcut_result_from_dict,
)
from .transcript_packer import format_packed_transcript, pack_transcript
from .semantic_chunker import build_semantic_chunks, chunks_to_chapters
from .story_mapper import STORY_ROLES, map_story_roles
from .topic_detector import detect_topic_shifts, extract_keywords, topic_shift_score

__all__ = [
    "ChapterBoundaryCandidate",
    "ChapterMetadata",
    "CutSafetyResult",
    "EDLSegment",
    "EditDecision",
    "PackedPhrase",
    "RoughCutResult",
    "RoughCutSegment",
    "RenderCommandPlan",
    "RenderExecutionResult",
    "SemanticChunk",
    "StoryboardCandidate",
    "StoryboardPlan",
    "SubtitleSegment",
    "STORY_ROLES",
    "TimelineEvent",
    "TimelineGap",
    "VisualSceneNote",
    "build_semantic_chunks",
    "build_edit_decisions",
    "build_edl_segments",
    "build_markdown_guide",
    "build_concat_render_plan",
    "build_ffmpeg_concat_command",
    "build_ffmpeg_extract_command",
    "build_ffmpeg_subtitle_burnin_command",
    "chunks_to_chapters",
    "classify_cut_safety",
    "detect_subtitle_gaps",
    "detect_topic_shifts",
    "edl_to_dict",
    "extract_keywords",
    "ffmpeg_available",
    "format_srt",
    "format_packed_transcript",
    "merge_close_gaps",
    "map_story_roles",
    "map_edl_segments_to_clip_sources",
    "pack_transcript",
    "run_roughcut_pipeline",
    "run_render_plan",
    "save_edl_json",
    "save_markdown_guide",
    "save_retimed_srt",
    "subtitle_from_dict",
    "subtitles_from_dicts",
    "topic_shift_score",
    "retime_subtitles_for_edl",
    "roughcut_result_from_dict",
    "write_concat_file",
]
