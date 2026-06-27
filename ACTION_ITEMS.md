<!--
Document-Version: 04.00.18-source-app
Phase: SOURCE_APP_CONTINUATION_V4_0_18
Last-Updated: 2026-06-27
Updated-By: Codex
Purpose: Consolidated active execution queue for the current source-app line.
-->
# ACTION_ITEMS.md - Active Execution Queue

This file is now the single source of truth for active performance ideas,
action items, execution order, QA gates, and rollback rules. Completed action
item history lives in `COMPLETED_ACTION_ITEMS.md`.

Former sources merged into this file:

- `idea_item.md`
- `NATIVE_LIB_PLAN.md`

Those standalone files were intentionally removed after consolidation.

## Hard Rules

- 자막 품질이 속도보다 우선이다.
- UI/UX는 명시 요청 없이 변경하지 않는다.
- 모델 축소, STT2 생략, LLM 생략, 품질 게이트 완화는 기본 최적화 후보가 아니다.
- Apple Silicon에서는 Apple Neural Engine, 즉 `ANE` 기준으로 표현한다. Core ML이 ANE/GPU/CPU 배치를 결정하고, Metal/MLX/whisper.cpp는 주로 GPU/CPU 경로로 검증한다.
- PyTorch MPS는 과거 `metal gpu stream` crash 근거가 있으므로 production default가 아니라 격리 실험 후보로만 둔다.
- owner 명시 재지시가 있기 전까지 native migration, Swift 재작성, 별도 네이티브 앱 전환은 active queue에 올리지 않는다.
- 자막 에디터 상호작용 표면은 2D-only이다. 자막 본문 편집, 자막 세그먼트 편집/생성/삭제, 플레이헤드 이동, 컷 경계, 다이아몬드, waveform/minimap 렌더링에 3D view, QML SceneGraph, OpenGL/Metal-backed UI surface를 새 default로 도입하지 않는다.
- 전체 앱 shell, 메뉴, 팝업, 다이얼로그의 기본값은 계속 `Qt Widgets` source app으로 유지한다. QML은 새 UI default에서 제외한다.
- 아이디어 발굴 또는 실행 전 `waste_action_item.md`와 `lesson_n_learned.md`를 먼저 읽고, 폐기된 아이디어를 새 근거 없이 반복하지 않는다.
- 실패/무효 후보는 `waste_action_item.md`에 hypothesis, change, metrics, quality, artifact, rejection reason을 남긴다.
- 반복하면 안 되는 진단/실험/운영 실수는 `lesson_n_learned.md`에 남긴다.
- owner 파일, 검증 절차, 구조 경계, 다음 세션 인수인계에 영향을 주는 변경은 같은 작업 안에서 관련 `docs/*.md`와 `docs/HANDOFF.md`까지 함께 갱신한다.
- 정상 완료된 idea/action item은 이 파일에서 삭제하고 `COMPLETED_ACTION_ITEMS.md`로 분리한다. 상세 검증 증거는 필요할 때 `test_result.md`, release note, `output/manual_verification/latest/`, `waste_action_item.md`, 또는 `lesson_n_learned.md`에 남긴다.

## Active Execution Queue

### 1. STT2 / Word Precision Generation Latency Profiling And Accuracy-Preserving Trim

Goal: The latest cut-boundary profile did not confirm cut-boundary work as the generation bottleneck. Continue the owner's generation-speed concern by measuring the real wall-clock cost of STT2 rescue, selective word timestamps, and downstream quality cleanup before proposing any behavior-preserving trim.

Status: active. Completed execution history is archived in `COMPLETED_ACTION_ITEMS.md#stt2--word-precision-generation-latency-profiling-and-accuracy-preserving-trim`. The open requirement is to keep `stt_recheck_collect_cache_enabled=false` and `stt_primary_collect_cache_enabled=false` by default, then run representative HeyDealer first-180s backfill for STT1 plus STT2/word collect caches when NAS is available again. If NAS remains off, stay in analysis/measurement-only work such as scheduling or memory-pressure variance.

Owner signal and current evidence:

- 2026-06-27: "지금 자막 생성이 너무 늦어지는데..."
- Cut-boundary closeout evidence: `output/manual_verification/latest/cut_boundary_latency_profile_20260627/latency_profile_report.md`
- HeyDealer 180s `profile_diagnostic` showed cut-boundary owner rows at `0.000602s` top cumulative time, while the same run still spent about one minute in the full High pipeline.
- Reference-scored HeyDealer 180s `mode_high` stayed stable at raw/final `58/56`, quality `81.335`, timing MAE `1.5958s`, final `overlap_count=0`, and `stable_for_save_reopen=true`.
- STT2/word profile evidence: `output/manual_verification/latest/stt2_word_precision_latency_20260627/latency_profile_report.md`
- New verifier evidence captures STT2/word counts, final invalid/non-monotonic/overlap stability, global canvas max-active stability, memory pressure, and generation-owner cProfile summaries.
- HeyDealer 180s non-profile repeat now shows pipeline elapsed `[65.648, 59.402]`, average `62.525s`, raw/final `58/55`, final `overlap_count=0`, `stable_for_save_reopen=true`, STT2 selected `37`, word precision `14`, memory pressure `critical`.
- HeyDealer 180s profile diagnostic points to generation owner rows, not cut-boundary rows: `stt_primary_transcribe=45.702069s`, `stt2_selective_recheck=27.404475s`, `word_precision=12.976476s`, `llm_refinement=16.734457s`, `subtitle_postprocess=17.731724s`, `cleanup_trim=0.085355s`; these are cProfile cumulative diagnostics, not elapsed truth.
- Reference-scored HeyDealer 180s `mode_high` remains stable at elapsed `62.640s`, raw/final `58/56`, quality `81.335`, text score `94.267`, timing MAE `1.5958s`, final `overlap_count=0`, `stable_for_save_reopen=true`, global canvas `max_active_segments=1`.
- Wall-clock stage-span evidence: `output/manual_verification/latest/stt2_word_precision_wall_clock_20260627/wall_clock_stage_report.md`
- HeyDealer 180s non-reference wall-clock probe: elapsed `65.222s`, raw/final `58/55`, final `overlap_count=0`, `stable_for_save_reopen=true`, global canvas `max_active_segments=1`, STT2 selected `37`, word precision `14`, memory pressure `critical`; stage spans: STT1 `18.162010s`, STT2 `14.360250s`, word precision `12.489603s`, VAD/STT consensus `0.000227s`, subtitle postprocess `20.108474s`.
- HeyDealer 180s reference-scored wall-clock benchmark: elapsed `65.824s`, raw/final `58/56`, quality `81.335`, text score `94.267`, timing MAE `1.5958s`, final `overlap_count=0`, `stable_for_save_reopen=true`, global canvas `max_active_segments=1`; stage spans: STT1 `19.519015s`, STT2 `14.229755s`, word precision `12.560951s`, VAD/STT consensus `0.000222s`, subtitle postprocess `19.406983s`.
- First safe trim evidence: `output/manual_verification/latest/stt2_word_precision_llm_defer_20260627/llm_defer_report.md`
- Change applied: macro LLM mode now defers runtime LLM model resolution and Ollama warmup until after the gate proves `llm_rows > 0`; zero-candidate rows no longer prepare a local LLM that will not be called.
- HeyDealer 180s post-trim non-profile repeat: pipeline elapsed `[65.317, 61.873]`, average `63.595s`, raw/final `58/55`, final `overlap_count=0`, `stable_for_save_reopen=true`, global canvas `max_active_segments=1`, STT2 selected `37`, word precision `14`, memory pressure `critical`.
- HeyDealer 180s post-trim reference-scored benchmark: elapsed `66.007s`, raw/final `58/56`, quality `81.335`, text score `94.267`, timing MAE `1.5958s`, final `overlap_count=0`, `stable_for_save_reopen=true`, global canvas `max_active_segments=1`; stage spans: STT1 `18.117848s`, STT2 `14.458806s`, word precision `20.851735s`, VAD/STT consensus `0.000197s`, subtitle postprocess `12.518010s`.
- Result interpretation: correctness and quality passed, and subtitle postprocess dropped in the reference run, but total elapsed did not materially improve because word precision variance rose. Keep the latency item active.
- Rejected candidate evidence: `output/manual_verification/latest/stt2_word_precision_context_batch_20260627/context_batch_rejection_report.md`
- Rejected candidate: batching two High context-boundary LLM pair checks into one Ollama request reduced reference subtitle postprocess to `9.879991s`, but changed one boundary/word decision and slightly regressed reference quality `81.335 -> 81.316`, text `94.267 -> 94.241`, and segmentation `87.879 -> 87.812`; code and tests for the batch path were reverted.
- Substage timing evidence: `output/manual_verification/latest/stt2_word_precision_substage_timing_20260627/substage_timing_report.md`
- New stage-span detail: `stt2_selective_recheck` and `word_precision` now expose `prepare_elapsed_sec`, `collect_elapsed_sec`, `annotate_elapsed_sec`, and `batch_elapsed_sec` in `stage_wall_clock_summary` spans and repeat-summary rollups.
- Local 60s reference smoke confirmed the new metrics are populated: STT2 total `11.258246s` with collect `11.201352s`; word precision total `4.368781s` with collect `4.304654s`; prepare/annotate were below `0.1s`; final overlap `0`, `stable_for_save_reopen=true`, global max active `1`.
- Collect fallback precision evidence: `output/manual_verification/latest/stt_collect_fallback_precision_20260627/fallback_precision_report.md`
- New collect detail: `stt_collect_whisperkit_fallback` spans now expose WhisperKit empty/timeout fallback count, reason, source/fallback model, total/max elapsed, chunk counts, emitted segment count, and word timestamp mode in benchmark/verifier artifacts.
- Local 60s benchmark smoke: fallback count `2`, fallback total `7.962836s`, fallback max `7.493920s`; STT2 collect `10.661352s`, word precision collect `3.640260s`; final overlap `0`, `stable_for_save_reopen=true`, global max active `1`.
- Local 60s verifier smoke confirmed repeat-summary/CSV propagation: fallback count `2`, fallback total `14.900298s`, fallback max `7.530310s`; final overlap `0`, `stable_for_save_reopen=true`, global max active `1`.
- High context-boundary diagnostics evidence: `output/manual_verification/latest/stt_high_context_diag_x5_audio_20260627/high_context_diag_report.md`
- New accuracy-test detail: High context-boundary diagnostics now expose candidate pairs, skipped pairs, LLM calls, failed calls, changed pairs, max pairs, and elapsed time in benchmark/verifier stage spans, summary metrics, repeat JSON/CSV, and compact CLI output.
- X5 cached-audio 180s verifier probe: pipeline `74.919s`, raw/final `43/50`, final invalid/non-monotonic/overlap `0/0/0`, `stable_for_save_reopen=true`, global canvas max active `1`, STT2 selected `28`, word precision `9`, memory pressure `critical`; top stage `subtitle_postprocess=32.746457s`, detail top `high_context_boundary=32.230736s`, candidate/call/changed `4/4/0`, failed calls `0`.
- Accuracy interpretation: this X5 audio probe proves the new measurement surface only. It is not a reference-scored quality acceptance run because the HeyDealer media/SRT under `/Volumes/photo/...` and repo-local X5 reference SRT were unavailable in this session.
- Reference fixture availability evidence: `output/manual_verification/latest/reference_fixture_availability_20260627/reference_fixture_availability.md`
- Current reference preflight result: blocked for reference-scored quality acceptance because `/Volumes/photo/.../헤이딜러_최종.MP4` and matching `.srt` are missing; cached HeyDealer WAV exists and is fallback-only for instrumentation and structural-stability probes.
- 2026-06-27 owner test directive: the next generation-latency test must use the NAS HeyDealer 3-minute video, not X5 or fallback-only cached audio as a substitute.
- NAS HeyDealer 3-minute preflight evidence: `output/manual_verification/latest/heydealer_nas_reference_preflight_20260627/reference_fixture_availability.md`
- Latest NAS HeyDealer 3-minute preflight rerun: `output/manual_verification/latest/heydealer_nas_reference_preflight_20260627_latest/reference_fixture_availability.md`
- Latest NAS HeyDealer 3-minute accepted run: `output/manual_verification/latest/heydealer_nas_reference_180s_20260627_2215/reference_benchmark_report.md`
- Current NAS HeyDealer 3-minute result: pass. `/Volumes/photo` was mounted, the exact MP4/SRT pair was verified, `mode_high` on the first 180 seconds produced elapsed `60.187s`, raw/final/reference `58/56/89`, quality `81.335`, text `94.267`, timing MAE `1.5958s`, final invalid/non-monotonic/overlap `0/0/0`, `stable_for_save_reopen=true`, global canvas `max_active_segments=1`, and `evaluate_reference_benchmark_acceptance.py` returned `accepted=true`.
- STT2/word duration diagnostics evidence: `output/manual_verification/latest/stt_recheck_duration_diagnostics_20260627/diagnostics_report.md`
- Latest NAS HeyDealer diagnostic run: pass. Same MP4/SRT first 180 seconds produced elapsed `59.255s`, raw/final/reference `58/56/89`, quality `81.335`, text `94.267`, timing MAE `1.5958s`, final invalid/non-monotonic/overlap `0/0/0`, `stable_for_save_reopen=true`, global canvas `max_active_segments=1`, and acceptance returned `accepted=true`.
- Duration interpretation: STT2 `applied_count=1` is a single broad rescue range, not a safe single-segment trim target. The span requested `180.096s`, prepared `120.000s`, collected `37` segments, and applied `37` segment-level results. Word precision still spent `12.253285s` across `25` ranges, with `67.640s` requested and `89.690s` prepared audio. Do not trim STT2/word precision from count fields alone.
- STT2/word reason breakdown evidence: `output/manual_verification/latest/stt_recheck_reason_breakdown_20260627/reason_breakdown_report.md`
- Latest reason-breakdown NAS run: pass. Same MP4/SRT first 180 seconds produced elapsed `58.820s`, raw/final/reference `58/56/89`, quality `81.335`, text `94.267`, timing MAE `1.5958s`, final invalid/non-monotonic/overlap `0/0/0`, `stable_for_save_reopen=true`, global canvas `max_active_segments=1`, and acceptance returned `accepted=true`.
- Reason interpretation: STT2 selective recheck is a missing-voice rescue (`missing_voice/route_hint/low_score/empty_text=1/0/0/1`), so it is not a skip candidate on this fixture. Word precision selected `25` ranges but none were editor-selected, precision-review, needs-review, red/yellow, risk, or missing-word forced (`0/0/0/0/0/0/0`), so the next safe investigation should focus on collect scheduling/cache reuse or a decision-equivalence gate, not review-critical range removal.
- High context decision diagnostics evidence: `output/manual_verification/latest/high_context_decision_diagnostics_20260627/decision_diagnostics_report.md`
- Latest High context NAS run: pass. Same MP4/SRT first 180 seconds produced elapsed `59.559s`, raw/final/reference `58/56/89`, quality `81.335`, text `94.267`, timing MAE `1.5958s`, final invalid/non-monotonic/overlap `0/0/0`, `stable_for_save_reopen=true`, global canvas `max_active_segments=1`, and acceptance returned `accepted=true`.
- High context decision interpretation: candidate/skipped/call/failed/changed/max pairs were `2/55/2/0/0/8`; action counts keep/move/merge/invalid were `2/0/0/0`; correction requested/applied was `0/0`. The owner-required NAS fixture therefore points to a decision-equivalent no-change gate as the only safe High context-boundary speed candidate, not batching or broad skipping.
- High context keep-cache candidate evidence: `output/manual_verification/latest/high_context_keep_cache_20260627/keep_cache_report.md`
- Generated 3-minute fixture: `output/manual_verification/latest/high_context_keep_cache_20260627/synthetic_fixture/synthetic_high_context_keep_cache.mp4` plus matching `.srt`, duration `180.583s`, reference rows `54`.
- Latest generated-video validation evidence: `output/manual_verification/latest/generated_video_subtitle_validation_20260628/validation_report.md`; NAS was off, so the Dex-generated 180s Korean fixture was revalidated with a fresh `mode_high` run `20260628_000644`: elapsed `78.344s`, raw/final/reference `54/54/54`, quality/text/timing `80.153/91.676/1.437s`, final invalid/non-monotonic/overlap `0/0/0`, save/reopen stable `true`, global max active `1`, `accepted=true`.
- Synthetic keep-cache result: pass. First write run `20260627_231459` produced raw/final/reference `54/54/54`, quality `80.153`, text `91.676`, timing MAE `1.437s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`, High context candidates/calls/cache hit-miss-write `8/8/0-8-8`, accepted `true`. Second cache-hit run `20260627_231734` kept the same quality/final gates, changed High context calls/cache hit-miss-write to `0/8-0-0`, and dropped High context elapsed `67.699701s -> 0.003326s`; accepted `true`.
- NAS status: owner turned NAS off and explicitly requested generated video/subtitle validation. No NAS cache-hit benchmark is claimed for this slice; run a real-media backfill when NAS is available again.
- Macro proofread response cache evidence: `output/manual_verification/latest/macro_response_cache_20260627/macro_response_cache_report.md`
- Synthetic macro-cache result: pass. First replay-cache write run `20260627_233240` produced raw/final/reference `54/54/54`, quality `80.153`, text `91.676`, timing MAE `1.437s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`, proofread elapsed `30.731199s`, accepted `true`, and wrote one macro response cache entry with 14 raw provider chunks. Second cache-hit run `20260627_233531` kept the same quality/final gates, showed `llm_macro_response_cache_hit_group_count=1`, `llm_macro_provider_called_group_count=0`, dropped proofread elapsed `30.731199s -> 0.545337s`, and accepted `true`.
- Macro-cache interpretation: cached provider chunks are still re-run through candidate-lock/verifier/Deep rerank on replay. This avoids the external Ollama call for an exact prompt/model/settings repeat without bypassing subtitle-quality policy.
- STT2/word collect cache evidence: `output/manual_verification/latest/stt_recheck_collect_cache_20260627/collect_cache_report.md`
- Synthetic STT collect-cache result: pass. First write run `20260627_234839` produced elapsed `46.498s`, raw/final/reference `54/54/54`, quality `80.153`, text `91.676`, timing MAE `1.437s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`, STT2 collect `14.284272s`, word precision collect `10.930693s`, cache hit/write/provider `false/true/true`, and accepted `true`. Second cache-hit run `20260627_234935` kept the same scored quality/final gates, dropped STT2 collect to `0.0s` and word precision collect to `0.0s`, showed cache hit/write/provider `true/false/false` for both stages, elapsed `20.105s`, and accepted `true`.
- STT collect-cache interpretation: cached provider output is re-run through annotation, STT2 replacement selection, word precision timing application, final integrity, and reference acceptance. Live STT2 preview callback paths disable the cache so candidate-lane preview events are not skipped. Default remains `stt_recheck_collect_cache_enabled=false` until representative real-media backfill is accepted.
- STT1 primary collect diagnostics evidence: `output/manual_verification/latest/stt_primary_collect_diagnostics_20260628/stt_primary_collect_report.md`
- Latest generated-fixture STT1 diagnostic run `20260628_001645`: pass, elapsed `49.380s`, raw/final/reference `54/54/54`, quality/text/timing `80.153/91.676/1.437s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`, `accepted=true`. STT1 total `20.135353s` was dominated by collect `19.986159s`; setup was `0.046327s`, chunks `2`, submitted `2`, worker count `2`, backend `whisperkit_persistent`, worker cache hit `false`. Interpretation: no behavior-preserving STT1 skip/model-downgrade/window-shrink trim is accepted from this slice.
- NAS-off stage/memory variance evidence: `output/manual_verification/latest/stt_latency_stage_variance_20260628/stage_variance_summary.md`
- New analysis-only tool: `tools/summarize_stage_variance.py` reads existing `benchmark_results.json` artifacts and summarizes elapsed variance, stage totals, cache hit/provider-call flags, memory-pressure distribution, final overlap/global-canvas gates, and duration-bound failures without changing runtime behavior.
- Latest NAS-off variance result over 10 generated/cache benchmark artifacts: elapsed avg/min/max/range `41.66/1.312/82.433/81.121s`; stage ranges STT1 `20.134950s`, STT2 `15.939524s`, word precision `20.271760s`, subtitle postprocess `30.410655s`; worst memory pressure counts `unknown=4`, `normal=4`, `critical=2`; invalid/non-monotonic/overlap/global max-active gates stayed all pass, while old tail-collapse generated runs are explicitly flagged as duration-bound failures and the fixed `20260628_013224` run stays within the `0.25s` slack.
- Jammini/서린 NAS-off review: `.agents/sentinel/handoffs/20260628-025200-stt-latency-nas-off-variance-review.md` returned `HOLD` for algorithm/default changes while NAS remains unavailable; allowed scope is analysis/measurement only.
- STT1 primary collect cache evidence: `output/manual_verification/latest/stt_primary_collect_cache_20260628/primary_collect_cache_report.md`
- Synthetic STT1 collect-cache result: pass. First write run `20260628_003224` produced elapsed `51.964s`, raw/final/reference `54/54/54`, quality/text/timing `80.153/91.676/1.437s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`, STT1 collect `17.717081s`, cache hit/write/provider `false/true/true`, and `accepted=true`. Second cache-hit run `20260628_003326` kept the same scored quality/final gates, dropped STT1 collect to `0.0s`, kept backend/model diagnostics as `whisperkit_persistent` / `whisperkit-persistent:large-v3-v20240930_turbo_632MB`, showed cache hit/write/provider `true/false/false`, elapsed `37.715s`, and `accepted=true`.
- STT1 collect-cache interpretation: cached provider output is still followed by STT2 selection, word precision, VAD/STT consensus, LLM/LoRA postprocess, final integrity, and reference acceptance. Live preview callback paths disable this cache so STT1 preview events are not skipped. Default remains `stt_primary_collect_cache_enabled=false` until representative real-media backfill is accepted.
- Combined collect cache evidence: `output/manual_verification/latest/combined_collect_cache_20260628/combined_collect_cache_report.md`
- Synthetic combined-cache result: pass. Owner kept NAS off, so the same generated 180s fixture was used to prove STT1, STT2, word precision, and macro proofread replay together. First write run `20260628_004231` produced elapsed `72.570s`, raw/final/reference `54/54/54`, quality/text/timing `80.153/91.676/1.437s`, final invalid/non-monotonic/overlap `0/0/0`, global max active `1`, STT1/STT2/word collect `17.752132s/14.261639s/10.621729s`, macro proofread `28.907253s`, and `accepted=true`. Second cache-hit run `20260628_004504` kept identical scored quality/final gates, dropped STT1/STT2/word collect to `0.0s/0.0s/0.0s`, showed provider calls `false` for all three collect stages plus macro cache hit/provider groups `1/0`, produced elapsed `4.449s`, generated final SRT block count `54`, SRT invalid/non-monotonic/overlap `0/0/0`, and `accepted=true`.
- Combined-cache interpretation: the code change only normalizes exact replay cache keys so unrelated cache enable/path/max-entry controls do not invalidate STT1 or STT2/word collect entries. Defaults remain off and live preview callback paths still disable collect replay.
- Macro cache warmup-skip evidence: `output/manual_verification/latest/macro_cache_warmup_skip_20260628/macro_cache_warmup_skip_report.md`
- Synthetic warmup-skip result: pass. With the combined cache files already populated, run `20260628_005314` proved the cache-hit macro path no longer resolves/warmups the local LLM when every LLM macro candidate group has an exact response-cache hit. Elapsed dropped `4.449s -> 1.312s` versus the prior combined cache-hit run, macro proofread detail dropped `3.606041s -> 0.400186s`, macro hit/write/provider groups stayed `1/0/0`, raw/final/reference stayed `54/54/54`, quality/text/timing stayed `80.153/91.676/1.437s`, final invalid/non-monotonic/overlap stayed `0/0/0`, global max active stayed `1`, generated SRT invalid/non-monotonic/overlap stayed `0/0/0`, and acceptance returned `true`.
- Macro warmup-skip interpretation: provider preparation is skipped only when all macro LLM groups are already cached; any cache miss or uncertain preflight falls back to the previous resolve/warmup path. The replay still runs candidate-lock verification, subtitle verifier, Deep rerank, final integrity, and reference acceptance.
- Latest NAS-off generated-video validation evidence: `output/manual_verification/latest/generated_video_subtitle_validation_20260628_latest/validation_report.md`
- Latest strict duration-bound validation evidence: `output/manual_verification/latest/generated_video_strict_duration_validation_20260628/strict_duration_report.md`
- Latest NAS-off generated-video result: fail under the stricter owner-requested verification method. The legacy benchmark acceptance still returned `accepted=true` for run `20260628_010403` with elapsed `44.968s`, raw/final/reference `54/54/54`, quality/text/timing `80.153/91.676/1.437s`, and final invalid/non-monotonic/overlap `0/0/0`; however, direct SRT/media validation found video duration `180.584s`, generated last end `182.032s`, `17` rows beyond video duration, `16` segments under `0.3s`, and one `59.792s` tail segment. Do not use this generated-fixture result as production-acceptable until duration-bound/min-duration gates are added to acceptance and the tail-collapse cause is fixed.
- Tail-collapse fix evidence: `output/manual_verification/latest/generated_video_tail_collapse_fix_20260628/tail_collapse_fix_report.md`
- Latest generated-video fixed result: pass under strict acceptance. Benchmark `20260628_013224` produced elapsed `44.307s`, raw/final/reference `54/54/54`, quality/text/timing `93.411/91.676/0.1391s`, final invalid/non-monotonic/overlap `0/0/0`, final last end/duration bound `180.12/180.584`, short/long segment counts `0/0`, global max active `1`, and `accepted=true`.
- Rejected prepared-clip reuse evidence: `output/manual_verification/latest/recheck_prepared_clip_reuse_rejected_20260628/recheck_prepared_clip_reuse_rejection_report.md`
- Rejected prepared-clip reuse interpretation: metadata sidecar reuse of prepared STT2/word clips did not materially reduce prepare time (`word prepare` stayed about `0.50s`) and added state-lifetime complexity, so the code/tests were reverted and only the rejection record remains.
- X5 local reference smoke evidence: `output/manual_verification/latest/x5_local_reference_fixture_20260627/reference_benchmark_report.md`
- Local X5 60s reference result: materialized `.codex_work/bench/x5_120_3s_180_3s_reference.json` into a relative-time SRT and ran `mode_high` against `.codex_work/bench/x5_120_3s_180_3s.wav`; elapsed `29.831s`, raw/final `28/23`, quality `80.914`, timing MAE `0.5608s`, final invalid/non-monotonic/overlap `0/0/0`, global canvas `max_active_segments=1`.
- Local X5 interpretation: this restores a short-loop reference-scored smoke surface and points to `stt2_selective_recheck` collect time (`16.941212s`) on this slice, but it is not enough to approve a broad latency trim or replace the owner-required NAS HeyDealer 3-minute acceptance run.
- X5 project-reference 180s evidence: `output/manual_verification/latest/x5_project_reference_180s_20260627/reference_benchmark_report.md`
- X5 project-reference accepted result: media `output/_audio_fingerprint/X5_시승기_후반_32346f324ad776ce0fe2/X5_시승기_후반_cleaned.wav` is semantically aligned with `projects/X5_시승기_전반.assets/subtitles/final.srt`; elapsed `70.383s`, raw/final/reference `43/50/67`, quality `76.387`, text `90.767`, timing MAE `1.5457s`, final invalid/non-monotonic/overlap `0/0/0`, global canvas `max_active_segments=1`.
- X5 project-reference rejected mismatch: the same media with `projects/X5_시승기_후반.assets/subtitles/final.srt` is rejected by `tools/evaluate_reference_benchmark_acceptance.py` with quality `23.234`, text `4.756`, and timing MAE `3.3362s`; file/SRT preflight alone is not enough.
- X5 project-reference stage detail: accepted 180s run shows High context-boundary candidate/call/changed `3/3/0`, High context-boundary elapsed `27.148184s`, STT2 collect `12.320240s`, and word precision collect `13.386089s`.

Scope:

- `core/audio/`
- `core/engine/`
- `core/stt_mode/`
- `core/subtitle_quality/`
- `tools/verify_full_media_pipeline.py`
- `tools/benchmark_subtitle_pipeline_variants.py`
- `.codex_work/benchmarks/subtitle_pipeline_variants/`
- `output/manual_verification/latest/`

Execution order:

1. Keep the separated profiling method: non-profile repeat elapsed for speed truth, cProfile only for ownership diagnosis, reference benchmark for quality/timing truth.
2. Keep both `stt_recheck_collect_cache_enabled=false` and `stt_primary_collect_cache_enabled=false` by default. When NAS is available again, run a representative HeyDealer first-180s backfill for STT1 plus STT2/word collect caches before using cache speed deltas as production evidence. If NAS remains off, stay in analysis/measurement-only work such as scheduling or memory-pressure variance; do not skip STT1/STT2, downgrade models, shrink windows, remove word precision coverage, or loosen final stability gates.

Acceptance gates:

- Do not skip STT2, disable word precision, lower LLM/LoRA/VAD quality policy, shrink STT windows, promote Fast mode defaults, or loosen final subtitle stability gates.
- Do not use `stt2_selective_recheck.applied_count=1` as a trim signal by itself; first inspect `applied_segment_count`, `range_audio_sec`, `prepared_audio_sec`, and same-fixture reference quality.
- Do not remove word precision ranges from review flags without checking `selected_range_count`, `precision_review_range_count`, `needs_review_range_count`, `red_range_count`, `yellow_range_count`, `risk_range_count`, and `missing_word_range_count` on the accepted NAS fixture.
- Do not treat profiler elapsed as performance truth; use non-profile repeat elapsed for speed comparisons and profiler output only for ownership diagnosis.
- If final subtitle timing, counts, or segmentation change, run a reference-scored real fixture and keep `invalid_duration_count=0`, `non_monotonic_count=0`, `overlap_count=0`, and `stable_for_save_reopen=true`.
- Owner-level next-test gate is NAS HeyDealer first 180 seconds. The latest accepted fixture proof is `output/manual_verification/latest/heydealer_nas_reference_180s_20260627_2215/reference_benchmark_report.md`; if the NAS media or matching SRT becomes missing again, report blocked and do not substitute X5 or fallback cached audio to approve or tune latency changes.
- Do not batch High context-boundary LLM pair decisions unless a stricter parity guard first proves batch output is decision-equivalent to the per-pair path on the same rows.
- Do not skip or short-circuit High context-boundary checks only because a non-reference run reports `changed_pair_count=0`; first prove reference quality/text/timing/segmentation parity.
- Treat High context keep-cache as accepted for the owner-approved generated fixture only: second run must show cache hits and scored acceptance. For representative real footage, run a NAS or other owner-provided backfill before using the speed delta as production-wide proof.
- Treat macro proofread response cache as accepted for the owner-approved generated fixture only: replay must show cache hit/provider-call `1/0`, candidate-lock/verifier still active, and scored acceptance. For representative real footage, run a NAS or other owner-provided backfill before using the speed delta as production-wide proof.
- Treat STT2/word collect cache as accepted for the owner-approved generated fixture only: replay must show collect cache hit/provider-call `true/false`, annotation and final gates still active, and scored acceptance. Keep the default disabled until representative real footage is accepted.
- Treat STT1 primary collect cache as accepted for the owner-approved generated fixture only: replay must show collect cache hit/provider-call `true/false`, STT2/word/postprocess/final gates still active, and scored acceptance. Keep the default disabled until representative real footage is accepted.
- Treat combined collect-cache proof as accepted for the owner-approved generated fixture only: replay must show STT1/STT2/word collect cache hit/provider-call `true/false`, macro provider-call group `0`, final SRT overlap `0`, and scored acceptance. Keep defaults disabled until representative real footage is accepted.
- Treat macro warmup-skip as accepted for the owner-approved generated fixture only: every macro LLM group must be response-cache hit before LLM preparation is skipped; any miss/uncertainty must preserve the old provider preparation path. Keep using reference acceptance and final/SRT overlap gates before claiming speed.
- A media/SRT pair is not reference-fit just because `verify_reference_fixture_availability.py` passes; `evaluate_reference_benchmark_acceptance.py` must accept the scored run before it is used for trim decisions.
- Do not revive rejected shortcuts from `waste_action_item.md`: cleanup removal, Fast mode default promotion, STT window shrinking, or speed-only native adoption.
- If an experiment is slower, lower quality, or only wins on a short fixture while risking X5, add it to `waste_action_item.md` with metrics and rejection reason.

Rollback:

- Revert scheduling/cache/deferment changes before touching subtitle-generation algorithms or quality thresholds.
- Keep old STT/word precision behavior as the default until a measured pass proves the new path.

### 2. Mac App Store Submission Readiness

Goal: Track the work required to move the current macOS source app from development/QA state to a Mac App Store submission candidate.

Status: active planning item. Completed execution history is archived in `COMPLETED_ACTION_ITEMS.md#mac-app-store-submission-readiness`. Do not execute packaging/signing/upload/notarization/DMG steps until the owner explicitly asks.

Current baseline:

- Packaging scripts exist under `packaging/macos/`.
- `packaging/macos/AI Subtitle Studio.entitlements` enables App Sandbox, user-selected read/write, app-scope bookmarks, network client, and audio input entitlements.
- Readiness audit evidence: `output/manual_verification/latest/app_store_readiness_audit_20260627/app_store_readiness_audit.md`
- Submission target lock evidence: `output/manual_verification/latest/app_store_readiness_target_lock_20260628/app_store_readiness_audit.md`
- Non-code submission draft: `docs/APP_STORE_SUBMISSION_READINESS.md`
- Current target decision: Mac App Store `.pkg` is the primary submission target; Developer ID beta `.dmg` is a separate opt-in track and is not App Store submission proof.
- Current audit result: `local_packaging_ready=true`, `app_store_submission_ready=false`; the latest target-lock audit reports blocker count `14`.
- There is no current checked App Store `.app` / `.pkg` artifact in `dist/macos/`.
- Current blockers include missing signed `.app`, signed `.pkg`, sandbox smoke, App Store Connect validation artifact, Apple Distribution codesign identity, installer identity, privacy answers, export compliance answers, screenshots, support URL, review notes, age rating, and release notes.
- App Store packaging, notarization, DMG, upload, and release work remain opt-in.

Execution order:

1. Next owner-approved execution step: build the app bundle with `packaging/macos/build_app_bundle.sh`.
2. Sign nested binaries and the outer app with the correct Apple Distribution identity and `AI Subtitle Studio.entitlements`; do not rely on ad-hoc signing for submission proof.
3. Validate sandboxed app launch, file access, audio/STT, model/network access, save/reopen, export, and source-app QA smoke.
4. Build a signed App Store `.pkg` with `packaging/macos/build_app_store_pkg.sh` using `INSTALLER_IDENTITY`.
5. Run App Store Connect validation with `packaging/macos/upload_app_store_build.sh validate` or Transporter before any upload.
6. Prepare non-code submission material separately: privacy answers, sandbox entitlement explanation, export compliance, screenshots, support URL, version metadata, and release notes.

Acceptance gates:

- Do not upload, tag, release, notarize, build DMG, or submit to App Store Connect without explicit owner approval for that step.
- App Store proof requires signed `.app`, signed `.pkg`, strict `codesign` verification, package signature verification, sandbox smoke, and App Store Connect validation output.
- Do not claim App Store readiness from source-app pytest or QA alone.
- Keep user-visible UI/UX and subtitle quality behavior unchanged unless the owner explicitly approves submission-driven changes.

Rollback:

- Packaging/signing changes should remain isolated under `packaging/macos/` and release docs unless a runtime entitlement issue requires app code changes.
- If sandbox breaks normal editor workflows, stop packaging and create a separate sandbox-compatibility fix item before retrying submission packaging.

## Migration Status

- Native migration is not an active direction for this repository.
- Keep the current Python/PyQt6 source app as the working product line.
- Completed source-app NLE runtime adoption evidence is archived in `COMPLETED_ACTION_ITEMS.md#source-app-nle-runtime-adoption-and-migration-status`.
- Persisted NLE project fields remain gated; broader persistence/save/render/export ownership cleanup requires a fresh owner-approved item and compatibility gate.
- Revisit migration only if the owner explicitly reopens it with a new scope and acceptance gate.

## Parked Candidates

These are not active queue items. Before executing one, create a fresh quality
gate and rollback branch.

- Playhead-only dirty-rect repaint: 현재 single-owner 2D full-canvas repaint가 잔상을 막는다. Macau visual smoke로 잔상 없음이 증명될 때만 별도 실험.
- App command/snapshot acknowledgement cleanup: `guided-subtitle-run`과 `capture-snapshot`이 실제 작업은 시작/저장했는데 CLI 응답은 timeout 또는 queued로 남는 관찰이 있었다. 성능 핵심 경로는 아니므로 active item 뒤에, artifact 신뢰도 개선으로만 다룬다.

## Waste And Lessons

- 폐기 후보 상세: `waste_action_item.md`
- 반복 금지 교훈: `lesson_n_learned.md`
- 공식 테스트 결과: `test_result.md`

## Metadata

```yaml
app_version: "04.00.18"
document_version: "04.00.18-source-app"
phase: "SOURCE_APP_CONTINUATION_V4_0_18"
queue_source_of_truth: "ACTION_ITEMS.md"
commit_policy: "Commit only when the user explicitly asks."
product_priority: "Accuracy before speed; optimize generation time only with behavior-preserving changes."
```
