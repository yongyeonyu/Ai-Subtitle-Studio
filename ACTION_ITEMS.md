<!--
Document-Version: 03.15.00
Phase: PHASE2
Last-Updated: 2026-05-04
Updated-By: Codex
Purpose: Remaining work queue only.
-->
# ACTION_ITEMS.md - Remaining Work Queue

## Queue Policy

- This file contains only unfinished or parked work.
- Completed items must be removed instead of kept as history.
- Release history belongs in `RELEASE_v*.md`.
- Bootstrap and operating rules belong in `AGENTS.md`.
- Product overview belongs in `README.md`.
- Actual file tree belongs in `File_structure.txt`.

## Metadata

```yaml
app_version: "03.15.00"
document_version: "03.15.00"
phase: "PHASE2"
next_phase: "PHASE3_LORA_GROUND_TRUTH_TRAINING"
commit_policy: "Commit only when the user explicitly asks."
product_priority: "Accuracy before speed."
run_all_exclusions:
  - "PHASE4_iPad"
root_forbidden_files:
  - "create_all*"
  - "_backup*"
  - "STRUCTURE.txt"
  - "requirements.txt"
required_requirement_files:
  - "requirements-mac.txt"
  - "requirements-windows.txt"
no_touch_without_user_request:
  - "dataset/video_preview_cache/"
release_handoff_files:
  - "AGENTS.md"
  - "ACTION_ITEMS.md"
  - "File_structure.txt"
  - "README.md"
  - "latest RELEASE_v*.md"
```

## Active Work

### PHASE3_LORA_GROUND_TRUTH_TRAINING

Status: planned
Priority: highest
First step: `P3-LORA-01`

Goal:

Build a persistent LoRA-style personalization and optimization system that learns from the user's verified video plus ground-truth subtitle pairs. The system should improve future subtitle generation accuracy, subtitle style, line breaks, timing, audio preset selection, subtitle quality selection, gap rules, LLM model selection, and LLM prompt selection.

Principle:

The program is not optimized for the fastest draft. It is optimized for highly accurate subtitles on the first pass, even if processing takes longer. Phase 3 must reduce manual correction time by making the automatic result more correct.

#### Scope

- Import one video plus one subtitle pair.
- Import multiple media/subtitle pairs.
- Import a folder of training assets.
- Store all LoRA or personalization artifacts in one user-inspectable folder.
- Keep training data cumulative across app sessions.
- Deduplicate repeated samples, subtitle lines, prompt/result pairs, and metric rows.
- Show training states: waiting, in progress, complete, failed, skipped.
- Resume pending training automatically while the app is idle.
- Pause training when the user starts editing or media processing.
- Share one personalization service across single-file, multiclip, folder queue, iCloud, and NAS workflows.
- Keep file handling safe on macOS and Windows.

#### Ground-Truth Import

Media inputs:

- Accept video or audio files used by the user in previous subtitle work.
- Accept individual media files from the LoRA settings screen.
- Accept folders containing media and subtitle files.
- Pair media and subtitle files by exact basename first, normalized basename second, and user confirmation fallback last.

Subtitle inputs:

- Support SRT in the first implementation.
- Preserve the original ground-truth subtitle file as source evidence.
- Parse start time, end time, text, original line breaks, punctuation, and segment duration.
- Leave room for later JSON project subtitles, VTT, ASS, and plain transcript support.

Exclusion rules:

- Exclude text inside parentheses from spoken-subtitle learning because it is user-authored editorial text, not actual speech.
- Keep excluded parenthetical text in metadata for optional editorial-style analysis.
- Exclude empty subtitles, pure symbols, duplicated blank lines, and obvious export artifacts.
- Store exclusion reason codes so the user can inspect what was ignored.

#### Truth Table

The truth table is the canonical dataset that records how verified subtitles should look and where each decision came from.

Required fields:

- `media_id`
- `media_path`
- `subtitle_path`
- `segment_id`
- `start_sec`
- `end_sec`
- `duration_sec`
- `raw_ground_truth_text`
- `speech_training_text`
- `excluded_parenthetical_text`
- `line_break_pattern`
- `punctuation_pattern`
- `char_count`
- `cps`
- `detected_split_rule`
- `speaker_or_voice_hint`
- `source_hash`
- `dedupe_hash`
- `created_at`
- `updated_at`

Learned style targets:

- User's speaking tone.
- Preferred Korean subtitle phrasing.
- Preferred line breaks.
- Preferred max characters per subtitle.
- Preferred subtitle duration range.
- Preferred split and merge points.
- Preferred punctuation behavior.
- Preferred handling of filler words and repeated words.

#### Subtitle Rule Learning

Config update target:

- File: `core/runtime/config.py`
- Behavior: analyze imported ground-truth subtitles and hard-code only the top 20 most frequently confirmed split rules into `DEFAULT_SPLIT_RULES`.
- Safety: preserve the existing default structure and keep a backup or review path before changing code defaults.

Initial runtime template:

```python
DEFAULT_SPLIT_RULES = [
    "는데", "은데", "지만", "하지만", "어서", "아서",
    "가지고", "해서", "하고", "이고", "면서", "니까",
    "거든", "잖아", "있습니다", "습니다",
]
DEFAULT_SPLIT_PUNCTUATION = [".", "!", "?"]
DEFAULT_MAX_CHARS = 20
```

JSON rule store:

- Save all discovered split and line-break rules to JSON.
- Store frequency, confidence, examples, first seen time, last seen time, and source media references.
- Keep only the top 20 high-confidence rules in `config.py`.
- Keep the full learned rule set in JSON for LoRA and personalization use.
- Deduplicate rules by normalized Korean text and punctuation pattern.

#### Settings Search And Optimization

Objective:

For each ground-truth media/subtitle pair, run controlled experiments that generate candidate subtitles under different settings, compare them against the truth table, and save the best-performing configuration.

Settings to search:

- Audio preset and automatic audio routing.
- FFmpeg preprocessing values.
- Voice filter choice and filter-specific parameters.
- VAD model choice and VAD thresholds.
- Subtitle quality preset.
- Gap menu parameters, including subtitle gap adjustment and single-subtitle preservation.
- STT1 model and STT2 model.
- Subtitle LLM model.
- Roughcut LLM model when relevant.
- LLM provider when applicable.
- LLM prompt templates.
- Prompt wording, examples, constraints, and style instructions.
- Max characters, punctuation rules, segment duration limits, merge/split thresholds, and line-break policy.

Comparison metrics:

- Korean text edit distance.
- Character error rate.
- Word or eojeol-level error rate.
- Timing overlap score.
- Boundary start and end delta.
- Line-break match score.
- Punctuation match score.
- Parenthetical exclusion correctness.
- Segment split/merge F1 score.
- Human-readable final score.

Optimization strategy:

- Start from the current production pipeline.
- Run a baseline pass first.
- Run candidate setting bundles instead of random unbounded combinations.
- Prefer accuracy-first configurations even when they take longer.
- Cache audio extraction and intermediate STT results where the cache does not invalidate the experiment.
- Save the winning configuration with the exact reason it won.
- Save losing configurations and scores for future analysis, then deduplicate aggressively.

Outputs:

- Best setting bundle per media file.
- Best setting bundle per audio profile or scene profile.
- Best prompt bundle per subtitle style cluster.
- Global recommended defaults learned from all imported data.

#### Automation And Idle Training

Idle policy:

- Detect when the application has no active processing job.
- Detect when the user has not interacted with the UI for a safe idle window.
- If pending LoRA training data exists, start or resume training automatically.
- Pause immediately when the user starts editing or processing.
- Resume later without losing progress.

Optional cloud-assisted automation:

- Investigate whether Codex or ChatGPT automation can help generate, evaluate, and refine prompt candidates.
- Treat external automation as optional.
- Never send private user media or subtitles to cloud automation unless the user explicitly enables it.
- If cloud-assisted prompt search is enabled, store consent, provider, prompt, response, and evaluation result.

#### UI Requirements

LoRA settings screen:

- Import video files, subtitle files, and folders.
- Show paired assets and unmatched assets.
- Show training queue rows with status, progress, score, and last error.
- Show best setting bundle found so far.
- Show learned split rules and line-break rules.
- Show excluded parenthetical examples.
- Open the LoRA data folder from the UI.
- Pause, resume, and clear pending training jobs.

Inspection:

- Let the user inspect truth-table rows.
- Let the user inspect dedupe decisions.
- Let the user inspect best and worst generated candidates against ground truth.
- Let the user review learned config updates before applying them.

#### Storage

Preferred folder:

```text
dataset/lora_personalization/
├── manifest.json
├── truth_table.jsonl
├── training_queue.json
├── learned_split_rules.json
├── learned_line_break_rules.json
├── setting_trials.jsonl
├── prompt_trials.jsonl
├── best_settings.json
├── excluded_parentheticals.jsonl
└── dedupe_index.json
```

Storage requirements:

- The folder must be user-readable.
- The format must be stable enough to back up and move between machines.
- Paths must be normalized and cross-platform safe.
- Large intermediate files should be cacheable and removable.
- Source media should be referenced in place by default, not copied into the dataset.

#### Pipeline Integration

- Apply learned split and line-break rules before subtitle generation where safe.
- Apply learned prompt settings to subtitle LLM calls.
- Apply learned settings recommendations to audio preset, subtitle quality, and gap rules.
- Use the same shared personalization service for single-file, multiclip, folder queue, iCloud, and NAS.
- Keep fallback behavior intact when no LoRA data exists.
- Log when personalization is active and explain why a setting was chosen.

#### Safety And Quality

- Never train spoken subtitle style from parenthetical editorial text.
- Never overwrite user settings without a visible save or apply action.
- Never hide low-confidence training results.
- Keep an undo or backup path for `config.py` split-rule updates.
- Keep all training state resumable after app restart.
- Add tests for SRT parsing, parenthetical exclusion, dedupe, idle training state, settings trial scoring, and cross-platform paths.

#### Implementation Plan

1. `P3-LORA-01`: Design data models for truth table, training queue, learned rules, setting trials, and prompt trials.
2. `P3-LORA-02`: Implement SRT parser and parenthetical exclusion with unit tests.
3. `P3-LORA-03`: Implement media/subtitle pairing for single files and folders.
4. `P3-LORA-04`: Implement persistent LoRA storage folder and manifest.
5. `P3-LORA-05`: Implement dedupe index and storage compaction.
6. `P3-LORA-06`: Analyze ground truth for split rules, punctuation, line breaks, max chars, CPS, and duration.
7. `P3-LORA-07`: Save full learned line-break and split rules to JSON.
8. `P3-LORA-08`: Add safe `config.py` update path for top 20 learned `DEFAULT_SPLIT_RULES`.
9. `P3-LORA-09`: Build scoring metrics against ground-truth subtitles.
10. `P3-LORA-10`: Build settings trial runner for audio preset, subtitle quality, gap settings, LLM model, and prompt variants.
11. `P3-LORA-11`: Save best settings and trial history.
12. `P3-LORA-12`: Add idle trainer that runs only when the app has no active work and the user is idle.
13. `P3-LORA-13`: Add UI for import, queue status, progress, inspection, pause/resume, and learned data review.
14. `P3-LORA-14`: Integrate learned personalization into all processing modes.
15. `P3-LORA-15`: Add regression tests for single-file, multiclip, folder queue, iCloud, NAS, macOS paths, and Windows paths.
16. `P3-LORA-16`: Add detailed terminal logs explaining training progress, chosen settings, prompt choices, and accuracy scores.

#### Open Questions For Implementation

- Should the first version be strictly local-only, or may it optionally use cloud automation after explicit consent?
- Which subtitle formats besides SRT should be supported in the first implementation?
- Should imported ground-truth media be referenced in place, copied into a dataset folder, or selectable per import?
- Should top-20 split-rule updates be automatic after training or require a review/apply button?
- What maximum disk budget should the personalization folder enforce before compaction?

## Parked Work

### PHASE4_iPad

Status: parked
Reason: moved out of Phase 3 so LoRA ground-truth training can become the next major phase.

Parked identifiers:

- `P3-SF1`
- `P3-SF2`
- `P3-SF3`
- `P3-API1`
- `P3-API2`
- `P3-API3`
- `P3-API4`
- `P3-API5`
- `iPad-1`
- `iPad-2`
- `iPad-3`
- `iPad-4`
- `iPad-5`
- `iPad-6`
- `iPad-7`
