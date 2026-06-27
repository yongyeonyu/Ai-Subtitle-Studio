# Waste Action Items

## 2026-06-28

- `recheck_prepared_clip_metadata_reuse_cache_hit`: exact collect-cache hit에서 준비된 STT2/word WAV clip을 metadata sidecar로 재사용하는 방향
  hypothesis: STT2/word collect provider 출력은 캐시로 건너뛰어도 recheck clip 준비 시간이 남으므로, 준비 WAV까지 재사용하면 cache-hit elapsed를 더 줄일 수 있다.
  change: `_stt_word_precision`/`_fast_stt2_recheck` 디렉터리를 collect-cache enabled 조건에서 보존하고, metadata-matched prepared clip 재사용 경로와 단위 테스트를 임시 적용했다.
  metrics: prior warmup-skip hit `20260628_005314` elapsed `1.312s`, word prepare `0.527071s`, STT2 prepare `0.098612s`, macro proofread `0.400186s`; candidate runs `20260628_010037` elapsed `1.149s`, word prepare `0.496650s`, STT2 prepare `0.086384s`, macro `0.322706s`; `20260628_010050` elapsed `1.183s`, word prepare `0.512973s`, STT2 prepare `0.079436s`, macro `0.326570s`.
  quality: raw/final/reference `54/54/54`, quality/text/timing `80.153/91.676/1.437s`, final invalid/non-monotonic/overlap `0/0/0` 유지.
  artifact: `output/manual_verification/latest/recheck_prepared_clip_reuse_rejected_20260628/recheck_prepared_clip_reuse_rejection_report.md`
  rejection reason: prepare time이 의미 있게 줄지 않았고, metadata sidecar와 임시 directory retention은 속도 근거 대비 상태 수명 복잡도가 크다. 코드와 테스트는 되돌렸고 반복하지 않는다.

## 2026-06-27

- `high_context_boundary_llm_batch_default`: High 문맥 경계 LLM pair 검수를 비중첩 쌍 단위로 한 번의 Ollama JSON 호출에 배치하는 방향
  hypothesis: 문맥 경계 후처리에서 같은 prompt/모델을 두 번 호출하는 비용을 한 번으로 줄이면 subtitle postprocess elapsed를 줄일 수 있다.
  change: `core/engine/subtitle_context_refiner.py`에 비중첩 pair batch prompt/parse/default decision 경로를 임시 적용하고, `tests/test_subtitle_context_refiner.py`에 batch/fallback 단위 테스트를 추가했다.
  metrics: HeyDealer 180s non-profile repeat는 pipeline elapsed `[69.223, 67.564]`, avg `68.393s`, raw/final `58/55`, final overlap `0`, `stable_for_save_reopen=true`, memory pressure `critical`; reference-scored run은 elapsed `64.222s`, raw/final `58/56`, subtitle postprocess `9.879991s`, word precision `20.835965s`.
  quality: reference quality `81.335 -> 81.316`, text `94.267 -> 94.241`, segmentation `87.879 -> 87.812`, timing MAE는 `1.5958s` 유지. 배치 LLM이 `경계/단어 보정 1쌍`을 적용해 per-pair 기준과 다른 결정을 냈다.
  artifact: `output/manual_verification/latest/stt2_word_precision_context_batch_20260627/context_batch_rejection_report.md`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260627_194512/benchmark_results.json`
  rejection reason: postprocess 시간은 줄었지만 기준 SRT 품질/text/segmentation이 소폭 하락했으므로 기본값으로 채택하지 않는다. 동일 row에서 per-pair 결정과 batch 결정이 완전히 같다는 parity guard가 생기기 전까지 반복하지 않는다.

## 2026-05-20

- `candidate2`: `cut_prescan_done`의 `cleanup=True` 제거
  결과: 마카오 avg `7.474` (`+10.40%` vs current), X5 avg `64.709` (`+5.64%` vs current)
  품질: 마카오/X5 모두 `final_segment_count`, `raw_segment_count`, `variant_score`, `rollback` 동일
  결론: prescan 직후 cleanup 제거는 장기 반복 비용을 줄이지 못했고, X5에서 오히려 느려졌다.
  artifact: `output/manual_verification/latest/20260520_perf_cycle3_candidate2`

- `candidate3`: `subtitle_optimize_done`의 warning-stage GPU trim 제거
  결과: 마카오 avg `6.682` (`-1.30%` vs current), X5 avg `63.007` (`+2.87%` vs current)
  품질: 마카오/X5 모두 `final_segment_count`, `raw_segment_count`, `variant_score`, `rollback` 동일
  결론: 짧은 클립에는 이득이 있었지만 X5 평균을 개선하지 못해 채택 가치가 부족했다.
  artifact: `output/manual_verification/latest/20260520_perf_cycle3_candidate3`

## 2026-05-21

- `phase1_unbounded_stage_metrics_status_payload`: status/guided-subtitle-status에 전체 stage history를 그대로 싣는 방향
  결과: 코드 리뷰 중 UDP command response가 `APP_COMMAND_BUFFER_SIZE=65535`를 넘길 위험을 확인했다.
  품질: 자막 결과에는 영향 없음.
  결론: full stage detail은 status 응답 기본값으로 쓰지 않는다. compact `resources + recent_events(8개)`만 노출하고, 상세 비교는 artifact JSON/로그로 남긴다.
  artifact: `output/manual_verification/latest/idea_full_execute_20260521-0228/summary.md`

- `candidate_full_parallel_stt_default`: STT1/WhisperKit과 STT2/MLX를 전체 구간에서 동시에 실행하는 High 기본값 후보
  결과: X5 60초에서 full-parallel은 `10.387~10.625s`로 selective `31.579~37.752s`보다 빨랐다.
  품질: final segment가 `24 -> 17`로 줄고 reference quality가 `72.986 -> 71.563`, timing MAE가 `0.647 -> 0.7392`로 나빠졌다.
  결론: 전체 STT1/STT2 병렬을 High 기본값으로 승격하지 않는다. 병렬 STT는 품질 barrier와 후속 word precision/segment-count 보정이 붙은 새 후보로만 재검토한다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260521_083704/benchmark_results.md`

- `native_policy_helper_default_without_parity`: Swift/native LLM candidate, deep rerank, LoRA scoring helper를 speedup만 보고 default 승격하는 방향
  결과: mini benchmark에서 speedup은 `20x~5000x`로 높게 나왔지만 parity check가 모두 실패했다.
  품질: LLM candidate count, deep chunks, batch count, LoRA top5 결과가 Python 기준과 맞지 않았다.
  보정: 이후 benchmark 설정이 experimental gate를 켜지 않아 disabled wrapper를 측정한 문제를 고쳤고, LoRA tie-break도 Python 순서에 맞춰 수정했다.
  결론: speed-only default 승격은 계속 폐기한다. corrected benchmark는 parity를 통과했지만 speedup이 `< 1.0`이라 default 승격하지 않는다.
  artifact: `tools/benchmark_native_policy_engine.py --docs 500 --rounds 12 --lora-rounds 2`

- `native_policy_helper_default_on_500doc_synthetic`: Swift/native LLM candidate, deep rerank, LoRA scoring helper를 corrected 500-doc synthetic benchmark 결과로 default 승격하는 방향
  결과: corrected benchmark에서 parity는 통과했지만 speedup은 `llm=0.308`, `deep=0.277`, `llm_batch=0.404`, `deep_batch=0.325`, `lora=0.382`.
  품질: LLM/deep/batch/LoRA top5 parity pass.
  결론: 현재 bridge/worker overhead가 더 커서 Python 유지. larger real index 또는 batch payload에서 새 speedup 근거가 나오기 전까지 default 승격하지 않는다.
  artifact: `output/manual_verification/latest/idea_full_execute_20260521-0821/native_policy_parity_20260521_0930.json`

- `mode_fast_as_quality_equivalent_x5_default`: X5 품질 동일 조건에서 `mode_fast`를 최종 기본 알고리즘으로 승격하는 방향
  결과: X5 60초 10회 반복에서 평균 `10.373s`로 빠르지만 quality gate `0/10`.
  품질: quality `71.514`, final segment `17`로 기준 `mode_high_piecewise_drift` quality `72.989`, final segment `24`보다 낮았다.
  결론: `mode_fast`는 Fast 모드 속도 후보로는 유지하되, 품질 동일 조건의 최종 기본 알고리즘으로 승격하지 않는다.
  artifact: `output/manual_verification/latest/idea_full_execute_20260521-0821/x5_modes_repeat10_quality_gate/repeat_summary.md`

- `empty_subtitle_output_as_speed_pass`: `full_media`에서 자막 0개 산출을 빠른 pass로 집계하는 방향
  결과: `qa_suite_full_20260521_100107`에서 `tinyping_auto_60s`가 `raw/final=0/0`인데 pass로 보일 수 있었다.
  품질: 실제 자막 산출이 없으므로 품질 보존 조건을 만족하지 않는다.
  결론: spoken/non-trivial slice의 raw 또는 final subtitle 0개는 무조건 실패다. 속도 개선 후보로 취급하지 않는다.
  artifact: `output/manual_verification/latest/qa_suite_full_20260521_100107`

- `mode_fast_as_quality_equivalent_x5_default_rerun`: X5 10회 재검증 후 `mode_fast`를 품질 동일 기본 알고리즘으로 다시 승격하는 방향
  결과: 2026-05-21 rerun에서 `mode_fast`는 평균 `10.250s`, p95 `11.410s`로 빠르지만 quality gate `0/10`.
  품질: quality `71.514`, readability `93.057`, timing MAE `0.7347`, final segment `17`로 `mode_high_piecewise_drift`의 quality `72.989`, readability `94.568`, timing MAE `0.6455`, final segment `24`보다 낮았다.
  결론: 같은 X5 reference 조건에서는 `mode_fast`를 품질 동일 기본 알고리즘으로 반복 제안하지 않는다. Fast 모드 속도 후보로만 유지한다.
  artifact: `output/manual_verification/latest/idea_full_execute_20260521-rerun/x5_modes_repeat10_current/repeat_summary.md`

- `forced_60s_quarter_window_default`: High rolling STT를 강제로 60초 창 4개로 쪼개 병렬 실행하는 방향
  결과: X5 180초 STT-only에서 `mode_high_piecewise_drift` `106.515s` 대비 forced 60초 quarter는 `128.951s`로 느렸다.
  품질: quality `77.315 -> 75.351`, final segment `57 -> 71`, raw segment `60 -> 79`로 과분할/품질 저하가 발생했다.
  결론: window 크기를 품질 기준과 다르게 줄여 1/4 분할을 강제하지 않는다. 기존 rolling window 크기를 유지한 guarded 병렬 수집만 사용한다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260521_134130/benchmark_results.md`

- `high_90s_aggressive_window_workers`: High rolling STT를 90초 창 3개로 줄여 더 많은 worker를 동시에 쓰는 방향
  결과: X5 180초 STT-only에서 현재 기본 `94.614s` 대비 `130.741s`로 느렸다.
  품질: quality `77.315 -> 76.587`, final segment `57 -> 69`, raw segment `60 -> 69`로 과분할/품질 저하가 발생했다.
  결론: 리소스 사용량을 늘리기 위해 window를 90초로 줄이지 않는다. X5에서는 180초 window가 더 빠르고 품질도 높다.
  artifact: `.codex_work/benchmarks/stt_resource_aggressive/20260521_140857/benchmark_results.json`

- `high_default_full_core_aggressive_short_fixture`: High 기본 preset에 Apple Silicon full-core aggressive benchmark profile을 바로 넣는 방향
  결과: 마카오 42초 smoke에서 3분 rolling window 이득은 없고, selective STT2 재검사 동안 MLX worker 재기동이 반복되어 실행 시간이 비정상적으로 늘어졌다.
  품질: 완료 전 중단. short fixture 기준 안정성/메모리 보호 실패로 판단.
  결론: full-core aggressive는 기본 High preset에 넣지 않는다. 필요하면 benchmark override 또는 긴 영상 전용 실험으로만 사용한다.
  artifact: `output/manual_verification/latest/20260521_macau_high_full_core_after_item1`

## 2026-05-23

- `high_stt2_overactive_threshold_82_budget36_default`: High/Precise 기본 STT2 선택 재검사 예산을 threshold `82`, max segments `36`, max audio `160s`, min improvement `1.0`으로 넓히는 방향
  결과: X5 High 180초에서 `quality_score=80.561`, `CER=0.168865`, `timing_mae_sec=0.7765`, `raw/final=64/62`, `elapsed_sec=139.900`으로 최신 정상 기준 `quality_score=87.402`, `CER=0.088391`, `timing_mae_sec=0.5742`, `raw/final=59/57`보다 나빠졌다.
  품질: STT2 후보가 `47 -> 35`로 과하게 넓어져 reference timing/text quality가 회귀했다.
  결론: Fast/Auto의 적극 STT2는 유지하되 High/Precise 기본값은 X5 검증된 bounded 예산 `threshold=78`, `max_segments=24`, `max_audio=110s`, `min_improvement=2.0`을 유지한다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260523_203930/benchmark_results.md`

- `final_micro_merge_preserve_direct_stt_rows_default`: 후단 보정에서 STT1/STT2가 직접 선택한 인접 자막 row를 기본적으로 병합하지 않는 방향
  결과: X5 High 180초에서 `quality_score=81.354`, `CER=0.174142`, `timing_mae_sec=0.6846`, `raw/final=47/61`로 최신 정상 기준 `quality_score=87.502`, `CER=0.084433`, `timing_mae_sec=0.5689`, `raw/final=59/56`보다 나빠졌다.
  품질: STT/final lane 모양은 일부 더 비슷해질 수 있지만, reference 기준 자막 텍스트/타이밍 품질과 segment 안정성이 떨어졌다.
  결론: STT row 보존을 후단 미세병합의 기본 정책으로 승격하지 않는다. 특정 화면/후보 표시 문제는 generation 품질 정책이 아니라 timeline/STT candidate display 또는 더 좁은 clamp 조건에서 다룬다.
  artifact: `output/manual_verification/latest/20260523_x5_native_stt_safe_fallback_timing/verification_summary.md`

- `whisperkit_streaming_task_level_audio_load`: Swift WhisperKit streaming worker에서 오디오 로드까지 worker task 안으로 넣어 load+transcribe를 동시에 더 강하게 밀어 넣는 방향
  결과: X5 High 180초에서 `elapsed_sec=89.965`로 직전 안전 기준 `83.744~84.101s`보다 느려졌다. Fast-STT2 종료 직후 memory `critical`로 STT persistent worker 재사용이 끊겼고, 단어정밀 단계가 새 Swift worker를 다시 시작했다.
  품질: `quality_score=87.502`, `CER=0.084433`, `raw/final=59/56`으로 품질은 유지됐다.
  결론: 오디오 로드까지 병렬 task에 넣는 공격적 방식은 메모리 pressure를 높여 long High run hot path를 악화시킨다. streaming worker는 task-level audio load를 기본값으로 쓰지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260523_043624/benchmark_results.json`

- `whisperkit_decode_options_reuse_helper`: Swift WhisperKit streaming worker에서 chunk마다 만들던 `DecodingOptions`를 request 단위로 한 번만 만들고 transcribe task body를 helper로 합치는 방향
  결과: X5 High 180초에서 `elapsed_sec=89.026`으로 최신 채택 기준 `82.942s`보다 느렸다. STT1 직후 memory `critical`로 persistent worker 재사용이 끊겼다.
  품질: `quality_score=87.502`, `CER=0.084433`, `raw/final=59/56`으로 품질은 유지됐다.
  결론: 작은 할당 감소보다 해당 run의 memory pressure/worker 재시작 비용이 더 컸고, 성능/메모리 gate를 통과하지 못해 되돌린다.
  artifact: `output/manual_verification/latest/20260523_whisperkit_decode_options_reuse_rejected/verification_summary.md`

- `whisperkit_payload_assembly_combined_text_fast_path`: Swift WhisperKit worker에서 `segments` payload와 top-level `text` payload 조립을 한 함수로 합치고, 흔한 single-result 경로를 빠르게 처리하는 방향
  결과: 1차 후보는 X5 High 180초에서 `elapsed_sec=83.848`로 직전 안전 기준 `83.238`보다 느렸고, 2차 single-result fast path 후보는 `elapsed_sec=91.076`으로 더 느려졌다.
  품질: 두 후보 모두 `quality_score=87.502`, `CER=0.084433`, `raw/final=59/56`으로 품질은 유지됐다.
  결론: top-level text 조립 미세 최적화는 long High run에서 유의미한 이득이 없었고, 2차 후보는 STT1/단어정밀에서 memory `critical` worker reuse break를 유발했다. 기존 검증된 `segmentPayloads` + top-level text 조립 경로를 유지한다.
  artifact: `output/manual_verification/latest/20260523_whisperkit_payload_assembly_rejected/verification_summary.md`

## 2026-05-24

- `high_force_silero_vad_quality_policy_for_x5`: High preset의 `selected_vad=silero`를 런타임 `vad_backend_policy=quality`로 강제해 ten_vad autotune을 막는 방향
  결과: X5 High 180초에서 VAD는 22개 Silero 구간으로 돌아왔지만 `quality_score=86.047~87.166`으로 최신 기준 `87.402`를 넘지 못했다.
  품질: STT2/word precision 개입이 늘면서 `아 이 시트! 시트 되게 편해요`, `그리고 이 차가 좋은 게` 같은 짧은 자막이 과분할되거나 끝부분 자막 수가 흔들렸다.
  결론: High 기본 VAD policy는 기존 `auto`를 유지한다. 실제 점수 회복은 VAD 강제가 아니라 word-timestamp 분할 보존 가드와 STT2 적용 범위 보호로 처리한다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260524_071634/benchmark_results.md`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260524_072651/benchmark_results.md`

- `stt2_partial_fragment_keep_with_base_default`: STT2 짧은 부분 조각이 STT1 긴 자막 일부와 겹칠 때 원 STT1과 STT2 조각을 둘 다 남기거나 부분 조각을 광범위하게 버리는 방향
  결과: X5 High 180초에서 둘 다 남기는 후보는 `quality_score=84.054`, 부분 조각 discard를 넓게 건 후보는 `quality_score=79.002`로 크게 회귀했다.
  품질: 전자는 중복/문맥 위험이 증가했고, 후자는 STT2 후보가 과하게 줄어 `raw/final=46/46`, reference 대비 `segment_count_delta=-12`가 됐다.
  결론: 병합 기본 정책을 넓게 바꾸지 않는다. STT2 부분 조각 문제는 더 좁은 fixture 기반 조건이 생기기 전까지 기존 병합 정책을 유지한다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260524_073530/benchmark_results.md`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260524_073917/benchmark_results.md`
