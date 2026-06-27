<!--
Document-Version: 04.00.18-source-app
Phase: SOURCE_APP_CONTINUATION_V4_0_18
Last-Updated: 2026-06-28
Updated-By: Codex
Purpose: Completed action item archive separated from ACTION_ITEMS.md.
-->
# COMPLETED_ACTION_ITEMS.md - Completed Action Item Archive

This file keeps completed action-item history out of `ACTION_ITEMS.md`.
`ACTION_ITEMS.md` remains the active execution queue and should contain only
remaining work, active gates, and rollback rules.

## STT2 / Word Precision Generation Latency Profiling And Accuracy-Preserving Trim

Source item: `ACTION_ITEMS.md` active queue item 1.

1. Verifier repeat artifacts now expose STT2/word counts, final stability gates, global canvas stability, memory pressure, and generation-owner profile summaries.
2. Same-fixture HeyDealer 180s baseline/profile/reference evidence was captured under `output/manual_verification/latest/stt2_word_precision_latency_20260627/`.
3. True wall-clock stage spans now cover STT1 primary transcription, selective STT2 rescue, word timestamp precision, VAD/STT consensus, and subtitle postprocess in both verifier and reference-scored benchmark artifacts.
4. First redundant LLM preparation candidate was implemented by deferring local model resolution/warmup until macro gate rows actually require LLM.
5. Post-trim verification used the stricter method: unit no-call guard, non-profile repeat, profiler diagnostic, and reference-scored fixture with quality/timing/final-stability metrics.
6. The High context-boundary LLM batching candidate was rejected and reverted because stricter reference scoring detected small quality/text/segmentation drift despite lower postprocess time.
7. Substage timing was added for STT2/word precision prepare/collect/annotate/batch phases so the next trim candidate can target the true substage instead of the broad stage bucket.
8. Collect fallback precision instrumentation was added so the next long-fixture run can separate true STT2/word precision collect work from WhisperKit empty/timeout fallback overhead.
9. High context-boundary pair diagnostics were added so optimization candidates can distinguish elapsed time from candidate count, LLM call count, failed calls, and actual changed-pair count.
10. `tools/verify_reference_fixture_availability.py` and focused tests were added so reference media/SRT readiness is checked before any latency trim can be treated as quality-accepted.
11. A local X5 60s reference-scored smoke fixture was restored from cached JSON rows and verified with `mode_high`; this remains short-loop evidence only.
12. A longer X5 180s project-reference smoke fixture was restored, and `tools/evaluate_reference_benchmark_acceptance.py` was added so semantically mismatched media/SRT pairs are rejected after scoring.
13. `/Volumes/photo` was mounted, the NAS HeyDealer MP4 plus matching SRT were verified, the owner-required 3-minute preflight/reference benchmark ran, and the scored result was accepted.
14. STT2/word precision range-audio, prepared-audio, and applied-segment diagnostics were added and verified on the same NAS HeyDealer 180s fixture with accepted reference scoring.
15. STT2/word precision reason-breakdown diagnostics were added and verified on the same NAS HeyDealer 180s fixture with accepted reference scoring.
16. High context-boundary decision-action diagnostics were added and verified on the same NAS HeyDealer 180s fixture with accepted reference scoring.
17. The strict High context-boundary keep/no-correction cache and benchmark `--setting` override surface were implemented; focused tests passed.
18. Benchmark CLI setting precedence was fixed so explicit `--setting` values win over mode-profile defaults; focused test covered the regression.
19. After the owner turned NAS off and requested generated video/subtitle validation, a 180.583s Korean synthetic fixture with 54 reference rows was created, two High-mode generation benchmarks ran, both scored results were accepted, High context keep-cache hits were proven to eliminate repeat LLM calls without changing final text/timing/overlap metrics, and a fresh NAS-off direct validation was rerun on 2026-06-28 with `accepted=true`, raw/final/reference `54/54/54`, and final invalid/non-monotonic/overlap `0/0/0`.
20. A macro proofread response replay cache was implemented. It stores exact prompt/model/provider response chunks and, on replay, still reruns candidate-lock/verifier/Deep rerank before preserving or rejecting the output; the owner-approved generated 3-minute fixture showed proofread postprocess `30.731199s -> 0.545337s` with identical scored quality/final gates and accepted reference results.
21. An opt-in STT2/word precision collect replay cache was implemented. It stores exact prepared-audio/model/settings collect output and, on replay, still reruns annotation, STT2 replacement selection, word precision timing application, final integrity, and reference acceptance; the owner-approved generated 3-minute fixture showed STT2 collect `14.284272s -> 0.0s`, word precision collect `10.930693s -> 0.0s`, elapsed `46.498s -> 20.105s`, and identical scored quality/final gates.
22. STT1 primary collect diagnostics were added and verified on the generated 3-minute fixture. STT1 primary transcribe is now split into setup/collect metadata; the latest run showed setup `0.046327s` and collect `19.986159s`, so no redundant setup/idle churn was accepted as an STT1 trim target.
23. An opt-in STT1 primary collect replay cache was implemented. It stores exact chunk-audio/model/settings collect output and, on replay, still runs STT2 selection, word precision, VAD/STT consensus, LLM/LoRA postprocess, final integrity, and reference acceptance; the owner-approved generated 3-minute fixture showed STT1 collect `17.717081s -> 0.0s`, elapsed `51.964s -> 37.715s`, and identical scored quality/final gates.
24. Exact replay cache keys were normalized so unrelated cache enable/path/max-entry controls do not cause duplicate STT1 or STT2/word provider work when multiple caches are enabled together; the owner-approved generated 3-minute fixture passed two combined-cache scored runs and produced a final SRT with invalid/non-monotonic/overlap `0/0/0`.
25. Runtime LLM model resolution and Ollama warmup are skipped when every LLM macro candidate group has an exact macro response cache hit; the owner-approved generated 3-minute fixture passed with elapsed `1.312s`, macro proofread `0.400186s`, identical scored quality/final gates, and generated SRT overlap `0`.
26. The owner-requested NAS-off generated-video validation was rerun on the current worktree. Benchmark `20260628_010403` accepted under the legacy score/overlap gate with raw/final/reference `54/54/54`, final/SRT invalid-nonmonotonic-overlap `0/0/0`, global max active `1`, and generated final SRT rows `54`.
27. Strict generated-video validation was promoted into the acceptance path. `tools/evaluate_reference_benchmark_acceptance.py` now probes media duration when possible and rejects final `last_end` beyond the media/window duration bound; generated benchmark summaries now expose final min/max segment duration plus short/long segment counts. Re-evaluating `.codex_work/benchmarks/subtitle_pipeline_variants/20260628_010403/benchmark_results.json` now returns `accepted=false` with reason `final_last_end_beyond_duration_bound`; artifact: `output/manual_verification/latest/generated_video_strict_acceptance_gate_20260628/reference_benchmark_acceptance.md`.
28. The generated-fixture tail collapse was fixed. `vad_stt_timing_consensus` now requires VAD/STT1 spans to be similar before the STT1/VAD-only union path can apply, preventing broad full-file VAD spans from stretching later STT1 rows. Re-run `20260628_013224` passes strict acceptance with final last end `180.12s`, short/long counts `0/0`, and no overlap.
29. The prepared recheck clip metadata reuse candidate was rejected and reverted because it did not materially reduce prepare time and added directory/metadata state complexity.
30. NAS-off stage/memory variance analysis tooling and evidence were added. `tools/summarize_stage_variance.py` generated `output/manual_verification/latest/stt_latency_stage_variance_20260628/stage_variance_summary.md` from existing cache/generated benchmark artifacts and confirmed this is analysis-only, not a production speed approval.

## Mac App Store Submission Readiness

Source item: `ACTION_ITEMS.md` active queue item 2.

1. `tools/audit_app_store_readiness.py`, `tests/test_app_store_readiness_audit.py`, and `docs/APP_STORE_SUBMISSION_READINESS.md` were added to keep App Store submission readiness evidence separate from source-app pytest/QA.
2. The submission target was locked to Mac App Store `.pkg`, and Developer ID beta `.dmg` was documented as a separate opt-in track that cannot count as App Store submission proof.

## Source-App NLE Runtime Adoption And Migration Status

Source section: previous `ACTION_ITEMS.md` migration status.

1. The completed internal NLE baseline is a source-app domain/adapter layer only. It does not reopen native migration, Swift rewrite, QML migration, or a visible Premiere-style UI clone.
2. Runtime NLE adoption evidence covers `gap_delete`, `gap_generate`, `caption_move`, `caption_resize`, `caption_split`, `caption_merge`, `caption_delete`, `candidate_confirm`, live editor `diamond` shared-boundary resize, live editor `square_left`/`square_right` boundary-handle resize, live editor segment delete-to-gap, live editor gap-generate, live editor diamond merge, live editor text/smart caption split, and live editor STT1/STT2 candidate-confirm routes through NLE dual-write.
3. NLE projection evidence covers final-overlay projection, global-canvas final-only projection, save/export final-caption projection for externalized final SRT/cache rows, NLE final-surface overlap guard, and roughcut saved-candidate render-plan projection.
4. NLE final-surface overlap guard evidence: `output/manual_verification/latest/nle_final_surface_overlap_guard_20260628/final_surface_overlap_guard_report.md`; one-frame final-surface micro-overlap is repaired to a shared boundary when the caption still keeps at least one frame, unfixable overlay/global-canvas overlap is not drawn as two active final captions, and save/export rejects unfixable final overlap before writing final SRT.
5. NLE persistence cutover audit evidence: `output/manual_verification/latest/nle_persistence_cutover_audit_20260628/nle_persistence_cutover_audit.md`; `prep_ready=true`, `persistence_cutover_ready=false`, runtime `NLEProjectState` hydration is proven through a saved roundtrip fixture, disk storage remains clean of `nle`, `nle_snapshot`, `_nle_project_state`, operation roundtrip passes for all 8 current NLE dual-write families, and persisted NLE disk-format cutover remains blocked until owner-approved compatibility gates exist. The first audit flagged legacy ID renumbering on `gap_generate`, `caption_split`, `caption_merge`, and `candidate_confirm`.
6. NLE global-canvas projection evidence: `output/manual_verification/latest/nle_global_canvas_final_projection_20260627/global_canvas_projection_report.md`; timeline canvas keeps live STT/subtitle preview rows, while global canvas can receive NLE `global_rows` filtered to final captions only.
7. NLE save/export projection evidence: `output/manual_verification/latest/nle_save_export_projection_cutover_20260628/save_export_projection_report.md`; externalized final SRT/cache rows now use NLE `save_export` final-caption projection while silence gaps stay in vector-canvas gap metadata and STT1/STT2 reference tracks remain separate.
8. NLE roughcut saved-candidate render-plan evidence: `output/manual_verification/latest/nle_roughcut_state_render_plan_cutover_20260628/roughcut_state_render_plan_report.md`; `roughcut_state` routes saved candidate `outputs.render_plan` construction through the NLE snapshot adapter with legacy render-command parity.
9. NLE live editor caption-merge evidence: `output/manual_verification/latest/nle_live_editor_caption_merge_cutover_20260628/caption_merge_cutover_report.md`; diamond merge attempts runtime NLE `caption_merge` dual-write for stable final captions while preserving Taption/source-app QTextDocument merge fallback for STT/live preview rows, NLE rejection, or unsupported shapes.
10. NLE live editor caption-split evidence: `output/manual_verification/latest/nle_live_editor_caption_split_cutover_20260628/caption_split_cutover_report.md`; text/smart split attempts runtime NLE `caption_split` dual-write for stable final captions while preserving Taption/source-app QTextDocument split fallback for STT/live preview rows, NLE rejection, or unsupported shapes.
11. NLE live editor candidate-confirm evidence: `output/manual_verification/latest/nle_live_editor_candidate_confirm_cutover_20260628/candidate_confirm_cutover_report.md`; STT1/STT2 candidate confirmation attempts runtime NLE `candidate_confirm` dual-write after the existing Taption/source-app placement logic computes final rows, while preserving fallback whenever NLE projection would alter source-app timing or sees unsupported rows.
12. NLE operation identity preservation evidence: `output/manual_verification/latest/nle_persistence_identity_preservation_20260628/nle_persistence_cutover_audit.md`; NLE shadow projection now preserves non-generic operation IDs, `candidate_confirm` maps generic `caption_1`/`caption_2` rows back to existing `subtitle_vector_*` identities, live editor block metadata carries `segment_id`, explicit `save-project` uses flushed current editor rows, and all 8 current NLE dual-write operation families reopen with `reopened_identity_preserved=true`. Final source-app quick QA evidence: `output/manual_verification/latest/qa_suite_quick_nle_identity_save_project_fix_20260628`.
13. Persisted NLE project fields remain gated, and broader persistence/save/render/export ownership cleanup remains gated.
