# Version: 03.01.31
# Phase: PHASE2
"""Local rough-cut engine helpers.

Phase2 keeps the analysis pipeline isolated from subtitle generation and
editing. Public functions here are intentionally pure where possible so they
can be tested without loading Qt, ffmpeg, or network services.
"""

from .gap_detector import TimelineGap, detect_subtitle_gaps, merge_close_gaps
from .boundary_refiner import BoundaryVerification, refine_major_boundaries, verify_major_boundary
from .chapter_segmenter import build_chapters
from .edit_decision_engine import CutSafetyResult, build_edit_decisions, classify_cut_safety, generate_cut_points
from .edl_generator import build_edl_segments, edl_to_dict, generate_edl, map_edl_segments_to_clip_sources, save_edl_json
from .guide_writer import build_markdown_guide, save_markdown_guide, write_markdown_guide
from .pipeline import run_roughcut_pipeline
from .renderer import render_from_edl
from .renderer_skeleton import (
    RenderCommandPlan,
    build_concat_render_plan,
    build_ffmpeg_concat_command,
    build_ffmpeg_extract_command,
    build_ffmpeg_subtitle_burnin_command,
    ffmpeg_available,
)
from .render_executor import RenderExecutionResult, run_render_plan, write_concat_file
from .scene_change_detector import FrameSample, SceneChange, detect_scene_changes
from .subtitle_retimer import format_srt, retime_subtitles_for_edl, save_retimed_srt
from .thumbnail_cache import ThumbnailCacheResult, default_thumbnail_cache_dir, ensure_thumbnail, thumbnail_cache_path
from .models import (
    ChapterBoundaryCandidate,
    ChapterMetadata,
    CutPoint,
    EDLSegment,
    EditDecision,
    PackedPhrase,
    RoughCutDraftState,
    RoughCutMinorGroup,
    RoughCutResult,
    RoughCutSegment,
    RoughCutTitleSuggestion,
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
from .roughcut_llm import RoughCutLLMActionResult, run_roughcut_llm_action
from .roughcut_prompts import build_roughcut_prompt, validate_roughcut_action_response
from .roughcut_settings import default_roughcut_settings, merge_roughcut_settings, roughcut_llm_enabled
from .title_suggester import build_title_suggestions
from .major_segmenter import build_major_roughcut_segments
from .transcript_packer import format_packed_transcript, pack_transcript
from .semantic_chunker import build_semantic_chunks, chunks_to_chapters
from .story_mapper import STORY_ROLES, classify_story_role, map_story_roles, remap_story_flow
from .topic_detector import detect_topic_shift, detect_topic_shifts, extract_keywords, topic_shift_score

__all__ = [
    "ChapterBoundaryCandidate",
    "ChapterMetadata",
    "BoundaryVerification",
    "CutPoint",
    "CutSafetyResult",
    "EDLSegment",
    "EditDecision",
    "PackedPhrase",
    "RoughCutDraftState",
    "RoughCutLLMActionResult",
    "RoughCutMinorGroup",
    "RoughCutResult",
    "RoughCutSegment",
    "RoughCutTitleSuggestion",
    "FrameSample",
    "SceneChange",
    "RenderCommandPlan",
    "RenderExecutionResult",
    "SemanticChunk",
    "StoryboardCandidate",
    "StoryboardPlan",
    "SubtitleSegment",
    "STORY_ROLES",
    "TimelineEvent",
    "TimelineGap",
    "ThumbnailCacheResult",
    "VisualSceneNote",
    "build_chapters",
    "build_major_roughcut_segments",
    "build_semantic_chunks",
    "build_edit_decisions",
    "build_edl_segments",
    "build_markdown_guide",
    "build_roughcut_prompt",
    "build_title_suggestions",
    "build_concat_render_plan",
    "build_ffmpeg_concat_command",
    "build_ffmpeg_extract_command",
    "build_ffmpeg_subtitle_burnin_command",
    "chunks_to_chapters",
    "classify_cut_safety",
    "classify_story_role",
    "detect_subtitle_gaps",
    "detect_topic_shift",
    "detect_topic_shifts",
    "detect_scene_changes",
    "default_roughcut_settings",
    "default_thumbnail_cache_dir",
    "edl_to_dict",
    "ensure_thumbnail",
    "extract_keywords",
    "ffmpeg_available",
    "format_srt",
    "format_packed_transcript",
    "generate_cut_points",
    "generate_edl",
    "merge_close_gaps",
    "merge_roughcut_settings",
    "map_story_roles",
    "remap_story_flow",
    "map_edl_segments_to_clip_sources",
    "pack_transcript",
    "render_from_edl",
    "refine_major_boundaries",
    "run_roughcut_pipeline",
    "run_render_plan",
    "run_roughcut_llm_action",
    "save_edl_json",
    "save_markdown_guide",
    "save_retimed_srt",
    "subtitle_from_dict",
    "subtitles_from_dicts",
    "topic_shift_score",
    "thumbnail_cache_path",
    "roughcut_llm_enabled",
    "retime_subtitles_for_edl",
    "roughcut_result_from_dict",
    "validate_roughcut_action_response",
    "verify_major_boundary",
    "write_concat_file",
    "write_markdown_guide",
]
