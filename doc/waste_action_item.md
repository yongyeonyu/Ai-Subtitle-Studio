# Waste Action Items

## 2026-06-02

- `case1 late-stage nonzero common-split word-text projection`: accepted case1 top gap-owner span `19.694 -> 26.432`에서 source/common-split은 그대로 둔 채, `restored_after_postprocess + split_count>=4 + digit long span`의 nonzero split row만 final cleanup 직전에 `words` 기반 local fragment로 재투영해 duplicate-drop 이후 reference gap을 메워보는 bounded downstream 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_220138_222627_72112/benchmark_results.json` 기준 `elapsed=3.865`, `quality=58.544`, `timing_priority_quality=60.744`, `timing_mae=0.7285`, `raw/final=6/15`였다. current accepted case1 `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_080210_685563_22342/benchmark_results.json`의 `1.624 / 66.468 / 68.999 / 0.5061`보다 runtime과 quality/timing이 모두 크게 나빠졌다.
  causal evidence: intended downstream owner는 실제로 움직였다. live log 기준 `llm_final`에서 `nonzero split 재투영 3개`가 발생했고 final segment 수가 `6 -> 15`로 늘었다. 하지만 그 직후 `[자막무결성-롤백] source_preservation:number_changed`와 STT anchor restore가 다시 발생해 broad split churn이 재도입됐다.
  결론: case1 top gap-owner span을 late-stage nonzero split word-text projection으로 살리는 방향도 채택하지 않는다. 같은 `late-stage nonzero common-split word-text projection` family는 다시 제안하지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_220138_222627_72112/benchmark_results.json`

- `case2 exact MLX large-v3 primary-route override`: case2 timing preset의 single-chunk `primary_collect` owner를 direct하게 흔들기 위해 `selected_whisper_model=mlx-community/whisper-large-v3-mlx`만 benchmark-only로 덮어, STT1을 exact MLX large-v3 primary route로 재검증하려는 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_222339_411161_97862/benchmark_results.json` 기준 `elapsed=167.546`, `quality=85.113`, `timing_priority_quality=85.44`, `timing_mae=0.4103`, `raw/final=15/13`이었다. current fast baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_200911_806838_39625/benchmark_results.json`의 `25.274 / 85.164 / 85.498 / 0.4076`보다 runtime과 quality/timing이 모두 나빠졌다.
  causal evidence: intended primary backend move는 실제로는 막혔다. live log에서 `⚡ [STT1] Apple NPU 우선 라우팅: mlx-community/whisper-large-v3-mlx -> whisperkit-persistent:large-v3-v20240930_626MB`가 먼저 찍혔고, 이어 `STT backend=whisperkit_persistent reason=explicit_whisperkit_model`로 실행됐다. 즉 current case2 primary owner는 `selected_whisper_model`만 exact MLX로 바꿔도 `mac_primary_fast_native_model`/native-route coercion에서 다시 WhisperKit으로 되돌아간다.
  결론: current case2에서 `selected_whisper_model`만 exact MLX route로 바꾸는 family는 true backend move를 만들지 못했고, one-shot 결과도 runtime과 quality/timing이 모두 더 나빴다. 같은 `exact MLX primary-route override` family는 다시 제안하지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_222339_411161_97862/benchmark_results.json`

- `case2 exact MLX primary-route override with fast-native/NPU disabled`: case2 timing preset에서 `selected_whisper_model=mlx-community/whisper-large-v3-mlx`에 더해 `stt_primary_fast_native_enabled=false`, `stt_npu_prefer_enabled=false`까지 benchmark-only로 줘서, 앞단 coercion을 끄고 exact MLX primary route가 실제로 들어가는지 재검증한 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_223021_769342_7176/benchmark_results.json` 기준 `elapsed=163.622`, `quality=85.113`, `timing_priority_quality=85.44`, `timing_mae=0.4103`, `raw/final=15/13`이었다. current fast baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_200911_806838_39625/benchmark_results.json`의 `25.274 / 85.164 / 85.498 / 0.4076`보다 runtime과 quality/timing이 모두 나빴다.
  causal evidence: 앞단 `Apple NPU 우선 라우팅` 로그는 사라졌지만, 그다음 단계에서 `STT backend=whisperkit_persistent reason=native_policy_whisperkit_ready`가 찍혔고 실제 모델도 다시 `whisperkit-persistent:large-v3-v20240930_626MB`로 실행됐다. 즉 current case2 primary owner는 `selected model`이나 fast-native/NPU preference가 아니라, 그 다음 단계 `select_stt_backend()`의 native backend policy에서 다시 WhisperKit으로 강제된다.
  결론: current case2에서 `selected_whisper_model` + `stt_primary_fast_native_enabled=false` + `stt_npu_prefer_enabled=false` 조합도 true MLX backend move를 만들지 못했고, one-shot 결과도 나빴다. 같은 `exact MLX primary-route override` family는 다시 제안하지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_223021_769342_7176/benchmark_results.json`

- `case2 numeric-core digit-phrase edge-shift salvage`: case2 timing preset에서 broad threshold relaxation 대신, pure-numeric는 제외하고 numeric core가 정확히 같은 digit phrase만 `candidate_edge_shift_exceeded` gate를 좁게 완화해보는 bounded apply-gate 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_214700_818085_57617/benchmark_results.json` 기준 `elapsed=131.612`, `quality=84.589`, `timing_priority_quality=84.813`, `timing_mae=0.45`, `raw/final=15/13`이었다. current fast baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_200911_806838_39625/benchmark_results.json`의 `25.274 / 85.164 / 85.498 / 0.4076`보다 runtime과 quality/timing이 모두 나빠졌다.
  causal evidence: intended owner는 실제로 움직였다. raw trace 기준 `계속 17.8인데`가 새로 `stt_word_precision_applied=true`로 열렸고, `word_precision_count 3 -> 4`가 됐다. 반대로 pure-numeric `11.4`와 truncated digit phrase `17.8에서 연비가 안 바뀌는데`는 계속 reject되어, 실험이 실제로 좁은 salvage 경계만 열었음이 확인됐다.
  결론: broad threshold relaxation보다 좁은 숫자-core digit phrase salvage여도 current case2에서는 quality/timing 회귀를 막지 못한다. 같은 `numeric-core digit-phrase edge-shift salvage` family는 다시 제안하지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_214700_818085_57617/benchmark_results.json`

- `case2 primary_collect timeout fallback 45s`: case2 timing preset의 single-chunk `primary_collect`에서 `stt_worker_response_timeout_sec`만 `150 -> 45`로 줄여, pathological WhisperKit completion-latency를 더 빨리 MLX fallback으로 넘기려는 bounded runtime-only 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_213636_729231_46372/benchmark_results.json` 기준 `elapsed=123.678`, `quality=70.352`, `timing_priority_quality=70.346`, `timing_mae=1.0404`, `raw/final=6/6`이었다. current fast baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_200911_806838_39625/benchmark_results.json`의 `25.274 / 85.164 / 85.498 / 0.4076`보다 runtime과 quality/timing이 모두 크게 무너졌다.
  causal evidence: intended owner는 실제로 움직였다. live log에서 `STT1`이 `45s`에 `stt_worker_timeout`으로 끊긴 뒤 `WhisperKit worker timeout → MLX GPU fallback`이 바로 발생했고, primary backend는 `whisperkit_persistent -> mlx`로 바뀌었다. 하지만 이후 low-score rescue shape가 `2 ranges -> 3 ranges`, `word precision_count 3 -> 0`, `stt2_selected_count 0 -> 1`, `segment_count 15 -> 6`으로 무너지면서 subtitle integrity가 크게 깨졌다.
  결론: `primary_collect` completion-latency를 silence-timeout fallback으로 잘라내는 방향은 current case2에서 broad quality collapse를 만든다. `stt_worker_response_timeout_sec`를 더 공격적으로 낮추는 같은 family는 다시 제안하지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_213636_729231_46372/benchmark_results.json`

- `case2 precision edge-shift threshold relaxation`: case2 timing preset에서 `stt_word_timestamps_precision_max_timing_shift_sec`를 `0.28 -> 0.55`로 올려, `candidate_edge_shift_exceeded`로 막히던 non-applied precision clip을 더 받아 timing을 끌어올려보는 방향
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_210623_396079_8029/benchmark_results.json` 기준 `elapsed=148.274`, `quality=84.111`, `timing_priority_quality=84.654`, `timing_mae=0.3909`였다. timing MAE만 소폭 좋아졌지만 current fast baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_200911_806838_39625/benchmark_results.json`의 `25.274 / 85.164 / 85.498 / 0.4076`보다 overall quality/timing과 runtime이 모두 나빠졌다.
  causal evidence: `word_precision_count`는 `3 -> 4`로 늘어 intended apply gate는 실제로 열렸다. 하지만 최종 단계에서 `[자막무결성-롤백] source_preservation:number_changed`가 발생했고, `quality_score`와 `timing_priority_quality_score`가 모두 내려갔다. broad threshold relaxation이 precision acceptance는 늘렸지만 subtitle integrity를 깼다는 뜻이다.
  결론: `candidate_edge_shift_exceeded`를 broad threshold relaxation으로 푸는 방향은 채택하지 않는다. 다음 시도는 global threshold를 올리기보다 subclip-local owner나 narrower non-skip apply owner를 봐야 한다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_210623_396079_8029/benchmark_results.json`

- `case2 word precision collect owner-runtime direct`: case2 timing preset에서 `STT-단어정밀` 8-chunk collect만 transient child worker 대신 owner runtime으로 직접 태워, current `word_precision collect` top owner를 줄여보는 additive runtime-only 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_201534_311885_46984/benchmark_results.json` 기준 `elapsed=25.748`, `quality=85.164`, `timing_priority_quality=85.498`, `timing_mae=0.4076`이었다. compare target인 current fast baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_200911_806838_39625/benchmark_results.json`의 `25.274 / 85.164 / 85.498 / 0.4076`보다 runtime이 느려서 repeat까지 갈 가치가 없었다.
  causal evidence: intended owner는 실제로 움직였다. `word_precision_collect_worker_source`는 `transient_child_worker -> owner_runtime_direct`로 바뀌었고 `word_precision_collect_submitted_chunk_count=8`도 유지됐다. 하지만 `collect_segments_ms 13643.094 -> 13733.447`로 collect subphase가 오히려 커졌고, elapsed도 `+0.474s` 악화됐다.
  결론: current case2의 `word_precision collect`에서는 owner-runtime direct가 causal move는 만들어도 runtime win은 못 만들었다. 같은 `word precision owner-runtime direct` family는 다시 제안하지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_200911_806838_39625/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_201534_311885_46984/benchmark_results.json`

- `case2 single-snapshot collect pressure decision`: `word precision collect`에서 pressure stage와 trace snapshot을 같은 `current_resource_snapshot()` 결과로 재사용해, `available_memory_snapshot_volatility`를 줄여보려는 additive runtime experiment
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_182458_836668_12635/benchmark_results.json` 기준 `elapsed=35.834`, `quality=85.164`, `timing_priority_quality=85.498`, `timing_mae=0.4076`으로 fresh slow baseline `29.36 / 85.164 / 85.498 / 0.4076`보다 명확히 느렸다.
  causal evidence: baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_174111_404723_62578/benchmark_results.json`과의 compare에서 `major_runtime_total_ms_delta=+6480.294`, `word_precision_runtime_total_ms_delta=+2954.504`, `collect_segments_ms_delta=+2909.447`였고, current collect state는 여전히 `pressure_stage=critical`, `pressure_reason_stage=critical`, `worker_source=transient_child_worker`였다.
  결론: single-snapshot 정합성 보정은 아이디어상 그럴듯했지만 case2 current owner를 개선하지 못했고 runtime만 악화시켰다. 같은 family는 현재 조건에서 다시 제안하지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_182458_836668_12635/benchmark_results.json`

- `case2 short-digit phrase collect prioritization`: scheduler fix 이후 `short_digit_phrase_collect_prioritization` family를 재검증하기 위해 case2 timing preset에 `계속 17.8인데` class만 앞당기는 short-digit collect prioritize hint를 추가한 additive ordering 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_165125_894726_27788/benchmark_results.json` 기준 `elapsed=20.352`, `quality=85.164`, `timing_priority_quality=85.498`, `timing_mae=0.4076`으로 fresh baseline `21.862 / 85.164 / 85.498 / 0.4076`보다 약간 빨라 보였다.
  causal proof: baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_154144_634637_8513/benchmark_results.json`과의 compare에서 `word_precision_submission_delta_rows=[]`, `word_precision_submission_index_changed_count=0`, `word_precision_submission_order_proven=false`였다.
  extra evidence: same compare에서 `word_precision_runtime_total_ms_delta=+2622.96`, `collect_segments_ms_delta=+2773.991`로 word precision owner는 오히려 악화됐다.
  결론: intended owner인 short-digit collect order가 artifact evidence로 증명되지 않았으므로 false win으로 판단한다. `short_digit_phrase_collect_prioritization` family는 다시 제안하지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_165125_894726_27788/benchmark_results.json`

- `case2 pure-numeric collect prioritize x2`: scheduler fix 이후 `phrase-linked pure-numeric collect prioritization` family를 재검증하기 위해 case2 timing preset의 `stt_word_timestamp_collect_prioritize_pure_numeric_max_offsets`를 `1 -> 2`로 늘리는 additive ordering 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_164528_286251_26552/benchmark_results.json` 기준 `elapsed=15.055`, `quality=85.164`, `timing_priority_quality=85.498`, `timing_mae=0.4076`로 fresh baseline `21.862 / 85.164 / 85.498 / 0.4076`보다 빨라 보였다.
  causal proof: baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_154144_634637_8513/benchmark_results.json`과의 compare에서 `word_precision_submission_delta_rows=[]`, `word_precision_submission_index_changed_count=0`, `word_precision_submission_order_proven=false`였다.
  결론: intended owner인 pure-numeric collect order가 artifact evidence로 증명되지 않았으므로 false win으로 판단한다. `stt_word_timestamp_collect_prioritize_pure_numeric_max_offsets`를 늘리는 같은 family는 다시 제안하지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_164528_286251_26552/benchmark_results.json`

- `case2 low-vad nondigit collect-defer`: `word precision collect`의 duration-first submission에서 `유지가 되고 있고요 / 변화가 없네` 같은 low-VAD nondigit non-applied clip만 뒤로 미는 additive ordering 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_163655_069161_24658/benchmark_results.json` 기준 `elapsed=15.377`, `quality=85.164`, `timing_priority_quality=85.498`, `timing_mae=0.4076`로 fresh baseline `21.862 / 85.164 / 85.498 / 0.4076`보다 빨라 보였다.
  causal proof: baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_154144_634637_8513/benchmark_results.json`과의 compare에서 `word_precision_submission_delta_rows=[]`, `word_precision_submission_index_changed_count=0`, `word_precision_submission_order_proven=false`였다.
  결론: intended owner인 collect submission order가 실제로 움직이지 않았으므로 false win으로 판단한다. 같은 `low_vad_nondigit collect-defer` family는 다시 제안하지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_163655_069161_24658/benchmark_results.json`

- `case2 precision worker cap 3->4`: case2 timing preset에서 `stt_whisperkit_word_timestamp_concurrent_workers`를 `3 -> 4`로 올려 `word_precision collect/transcribe` wallclock을 줄여보는 runtime-only 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_114940_041390_95651/benchmark_results.json` 기준 `elapsed=21.398`로 fresh pre-experiment baseline `20.983`보다 이미 느렸다.
  repeat: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_114939_880917_95654/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_115002_717974_96172/benchmark_results.json` aggregate `elapsed_mean=17.833`, `spread=7.36`으로 variance가 컸다.
  품질: `quality=85.164`, `timing_priority_quality=85.498`, `timing_mae=0.4076`로 점수는 유지됐지만 runtime-only win으로 보기엔 불안정했다.
  결론: case2 precision worker cap 증가는 채택하지 않는다. worker 수를 더 키우는 같은 방향은 다시 제안하지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_114940_041390_95651/benchmark_results.json`

- `case2 low-VAD nondigit precision skip`: `word precision` non-applied 6개 중 `비숫자 + metadata-only + low-VAD` 2개만 제외하는 bounded runtime-only 실험
  결과: prepared clip `9 -> 7`, non-applied clip duration `17.26s -> 10.48s`로 줄었지만 one-shot runtime은 `15.381s -> 20.685s`로 악화.
  품질: `quality=85.164`, `timing_priority_quality=85.498`, `timing_mae=0.4076`로 점수는 같았지만 runtime owner interaction이 더 나빠졌다.
  결론: 이 class skip은 runtime-only 개선으로 채택하지 않는다. 같은 방향의 broad `low-VAD nondigit precision skip`은 다시 제안하지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_102214_626330_80558/benchmark_results.json`

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

## 2026-06-02

- `apple_case2_retention_ratio_0_80_on_x5_slice`: Apple STT를 `STT2`로 두는 case2 timing variant에서 `stt_selective_recheck_min_segment_retention_ratio`를 `0.80`으로 완화하는 방향
  결과: X5 30초 slice에서 `elapsed_sec=18.696`으로 빨라졌지만 `quality_score=45.376`, `timing_priority_quality_score=47.891`, `timing_mae_sec=1.3389`, `final_segment_count=11`로 심하게 회귀했다.
  품질: Apple STT2 rescue가 `12개` segment로 대거 채택되면서 `stt2_selected_count=10`, `stt2_coverage_ratio=0.896854`가 됐지만, reference timing/text 품질과 segment 안정성이 무너졌다.
  결론: case2에서 segment retention guard를 `0.90 -> 0.80`으로 낮추는 완화안은 채택하지 않는다. case2 개선은 retention guard 완화가 아니라 replacement 품질 기준이나 rescue 범위 자체를 더 좁게 다뤄야 한다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_012139/benchmark_results.json`

- `apple_case2_selective_overlap_ratio_0_50`: case2 selective STT2 merge에서 retention ratio는 그대로 두고, replacement merge overlap만 `0.35 -> 0.50`으로 높여 원본 STT1 drop 범위를 줄여보는 방향
  결과: X5 30초 slice에서 direct Apple path cleanup 이후에도 `STT2 보강 결과가 원본 세그먼트를 과도하게 줄여 STT1 유지 (15개 → 10개)`가 그대로였고, `quality_score=86.995`, `timing_priority_quality_score=87.043`, `timing_mae_sec=0.4161`도 사실상 변하지 않았다.
  품질: `stt2_selected_count=0`, `recheck_applied_count=0`가 그대로라 실제 adoption에는 도움이 없었다.
  결론: overlap ratio만 키우는 additive knob은 case2 current bottleneck을 건드리지 못한다. 이 방향은 코드에 남기지 않고 되돌린다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_014601/benchmark_results.json`

- `apple_case2_min_improvement_0_0`: case2 selective STT2 replacement gate에서 `stt_low_score_recheck_min_improvement=0.0`으로 낮춰 Apple rescue가 조금만 나아도 채택되게 하는 방향
  결과: X5 30초 slice에서 `elapsed_sec=24.408`, `quality_score=86.995`, `timing_priority_quality_score=87.043`, `timing_mae_sec=0.4161`이었지만 `stt2_selected_count=0`, `recheck_applied_count=0`, `15개 → 10개` retention failure는 그대로였다.
  품질: 숫자는 유지됐지만 adoption 지표가 전혀 안 바뀌어서 current bottleneck을 건드렸다고 보기 어렵다.
  결론: current case2 병목은 `min_improvement`가 아니며, 이 knob은 코드에 남기지 않고 되돌린다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_015046/benchmark_results.json`

- `apple_case2_partial_salvage_enabled`: retention guard를 유지한 채, full merge가 실패할 때 per-range partial salvage fallback을 켜서 일부 STT2만 살리는 방향
  결과: X5 30초 slice에서 adoption은 실제로 생겼다 (`stt2_selected_count=7`, `recheck_applied_count=7`). 하지만 `quality_score=78.633`, `timing_priority_quality_score=79.349`, `timing_mae_sec=0.5244`, `final_segment_count=14`로 품질과 timing이 크게 무너졌다.
  품질: Apple STT2 rescue가 일부 구간에서 실제로 들어오긴 했지만, 현 조건에서는 잘못된 긴 span이 너무 많이 살아남아 baseline/case1/current case2 winner보다 명백히 나빠졌다.
  결론: partial salvage helper 자체는 future bounded experiments용으로 둘 수 있어도, case2 benchmark preset에는 연결하지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_015703/benchmark_results.json`

- `apple_case2_partial_salvage_similarity_0_80`: case2 timing preset에 partial salvage를 다시 켜되, `stt_rescue_similarity_threshold=0.80`으로 넓은 Apple rescue span을 더 강하게 거르는 방향
  결과: X5 30초 slice에서 `stt2_selected_count=4`, `recheck_applied_count=4`까지 adoption은 일부 생겼지만 `quality_score=83.668`, `timing_priority_quality_score=83.709`, `timing_mae_sec=0.5223`, `final_segment_count=14`로 current case2 winner보다 여전히 나빴다.
  품질: `80km/h로 크루즈 컨트롤끄라구요`, `178`, `114에서 또 안 바뀌네` 같은 Apple span 일부는 걸러졌지만, 남은 salvage도 reference 대비 timing/text fidelity를 충분히 못 지켰다.
  결론: similarity threshold를 `0.80`으로 올려도 partial salvage 자체를 case2 preset에 승격할 근거는 부족하다. helper/test는 유지해도 benchmark preset 연결은 다시 끈다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_020538/benchmark_results.json`

- `apple_case1_initial_word_timestamps_enabled`: case1 timing preset에서 Apple STT1의 initial transcribe 단계부터 `word_timestamps`를 켜서 더 풍부한 timing detail을 직접 받는 방향
  결과: X5 30초 slice에서 `stt2_selected_count=6`, `recheck_applied_count=6`까지 adoption은 생겼지만 `elapsed_sec=25.545`, `quality_score=46.420`, `timing_priority_quality_score=48.797`, `timing_mae_sec=1.3655`, `final_segment_count=17`로 크게 회귀했다.
  품질: richer Apple timing detail 자체는 들어왔지만, initial Apple STT1 shape가 current case1/case2 guard와 잘 맞지 않아 잘못된 merge/replacement가 늘고 `source_preservation:number_changed` rollback까지 연쇄로 발생했다.
  결론: `word_timestamps` capability와 native support는 유지해도, case1 benchmark preset에서 initial Apple STT1 `word_timestamps`를 직접 켜는 방향은 현재 조건에서 채택하지 않는다. 더 좁은 segmentation/timing experiment 없이 다시 기본 preset에 연결하지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_025847/benchmark_results.json`

- `apple_case1_decimal_suffix_clause_split`: Apple STT1 clause split에서 숫자 소수점과 조사 suffix(`80으로`, `17.8에서`)까지 적극적으로 split 후보로 넣어 case1 raw segmentation을 더 잘게 만드는 방향
  결과: case1에서는 `stt2_selected_count=9`, `recheck_applied_count=9`, `raw/final=14/12`까지 adoption이 늘었지만 `quality_score=64.835`, `timing_priority_quality_score=65.207`, `timing_mae_sec=0.9994`로 기존 accepted case1보다 timing/quality가 나빠졌다. 더 중요한 건 같은 코드로 case2가 일시적으로 `quality_score=72.649`, `timing_priority_quality_score=73.900`, `timing_mae_sec=0.5684`까지 무너졌다.
  품질: 더 공격적인 clause split이 Apple STT2 rescue span까지 바꿔 current case2 winner의 merge/replacement 균형을 깨뜨렸다.
  결론: 숫자/조사까지 포함한 aggressive Apple clause split은 case1 단독 개선처럼 보여도 case2 winner를 망가뜨리므로 채택하지 않는다. 실험은 즉시 되돌리고, 다음 case1 개선은 clause split이 아니라 `Fast-STT2 selective rescue variance` owner만 좁게 본다.

- `apple_case2_metadata_only_precision_guard_broad`: case2 timing에서 metadata-missing only Whisper STT1 low-score rows를 전부 precision 후보에서 빼는 방향
  결과: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_033711/benchmark_results.json` 기준 `elapsed_sec=12.591`로 빨라졌지만 `quality_score=85.001`, `timing_priority_quality_score=85.303`, `timing_mae_sec=0.4200`으로 기존 accepted winner보다 quality/timing이 내려갔다. `word_precision_count`는 `6 -> 1`까지 과하게 줄었다.
  품질: broad metadata-only guard는 실제로 필요한 일부 Korean phrase timing refinement까지 같이 잘라내서 timing/overlap 밸런스를 약하게 만들었다.
  결론: metadata-missing low-score row 전체를 한 번에 빼는 broad guard는 채택하지 않는다. 같은 아이디어를 다시 쓰더라도 digits/duration/VAD 조건으로 더 좁혀야 한다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_030609/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_030639/benchmark_results.json`

- `apple_case2_disable_missing_voice_recheck`: case2 timing preset에서 `missing_voice` rescue candidate 1개를 통째로 빼서 Fast-STT2 runtime만 더 줄여보는 방향
  결과: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_041108/benchmark_results.json` 기준 `elapsed_sec=13.625`로 빨라졌지만 `quality_score=80.525`, `timing_priority_quality_score=80.807`, `timing_mae_sec=0.5672`로 current winner보다 크게 악화됐다.
  품질: source counts는 `low_score=9`, `missing_voice=0`, `route_hint=0`, `merged=9`였고, 그 결과 `stt2_selected_count=7`, `recheck_applied_count=7`, `stt2_coverage_ratio=0.355067`까지 늘어 잘못된 STT2 adoption을 일으켰다.
  결론: case2에서는 `missing_voice` 후보 1개도 실제 merge 균형에 영향을 주므로 preset에서 통째로 끄지 않는다. 다음 시도는 source 제거가 아니라 remaining low-score candidate 자체를 더 좁게 보는 방향이어야 한다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_041108/benchmark_results.json`

- `apple_case2_numeric_only_metadata_skip`: case2 timing preset에서 `정확한 숫자만 있는 low-score row`를 STT2 rescue 후보에서 빼 runtime만 더 줄여보는 방향
  결과: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_042133/benchmark_results.json` 기준 `elapsed_sec=16.748`, `quality_score=85.164`, `timing_priority_quality_score=85.498`, `timing_mae_sec=0.4076`로 current winner와 사실상 동일했고, `recheck_source_counts`도 그대로 `low_score=9`, `missing_voice=1`, `route_hint=0`, `merged=6`이었다.
  품질: current case2 survivor 숫자 row들(`17.8`, `11.4`)은 `metadata-only`가 아니라 `low_language_char_ratio`까지 같이 붙어 있어, 새 numeric-only skip guard가 실제 candidate set을 전혀 줄이지 못했다.
  결론: 이 방향은 no-op이라 채택하지 않는다. 다음 시도는 숫자 row 자체를 건드리기보다, `low_language_char_ratio`와 long-phrase 숫자 row를 더 정확히 분리하는 쪽이어야 한다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_042133/benchmark_results.json`

- `apple_case2_short_numeric_phrase_skip`: case2 timing preset에서 남은 `숫자+문장` survivor 2개 중 `짧은 숫자-구문` 1개만 STT2 rescue 후보에서 빼 runtime을 더 줄여보는 방향
  결과: one-shot에서는 `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_044013/benchmark_results.json` 기준 `elapsed_sec=16.076`, `quality_score=85.164`, `timing_priority_quality_score=85.498`, `timing_mae_sec=0.4076`로 거의 같아 보였지만, repeat 2x에서는 `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_044042/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_044058/benchmark_results.json` 기준 `elapsed_mean=15.5815`, `spread=1.115`로 현재 accepted winner(`elapsed_mean=15.233`)보다 평균이 나빠졌다.
  품질: quality/timing 수치는 그대로였지만 runtime gain이 repeat에서 재현되지 않았고 variance도 커졌다. survivor는 `surviving_digit_rows=1`까지 줄었지만, 그 자체가 accepted 기준이 되진 않았다.
  결론: `짧은 숫자-구문`만 추가로 빼는 additive guard는 현재 accepted pure-numeric guard 위에 더 올릴 가치가 없다. 이 실험은 코드에 남기지 않고 즉시 되돌린다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_044013/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_044042/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_044058/benchmark_results.json`

- `apple_case2_long_numeric_phrase_skip`: case2 timing preset에서 남은 `숫자+문장` survivor 2개 중 `긴 숫자-구문` 1개만 STT2 rescue 후보에서 빼 runtime을 더 줄여보는 방향
  결과: artifact 기준 survivor는 실제로 `2 -> 1`로 줄었고 남은 row는 `계속 17.8인데` 1개만 남았다. 하지만 one-shot에서는 `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_053424_466325_49221/benchmark_results.json` 기준 `elapsed_sec=24.592`로 크게 느려졌고, repeat 2x에서도 `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_053424_299395_49222/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_053450_377153_49855/benchmark_results.json` 기준 `elapsed_mean=20.3165`, `spread=8.813`으로 current accepted case2 band(`one-shot=15.503`, `repeat mean=15.233`)보다 명확히 나빴다.
  품질: `quality_score=85.164`, `timing_priority_quality_score=85.498`, `timing_mae_sec=0.4076`는 그대로였지만, runtime regression이 너무 커서 accepted 기준을 통과하지 못했다.
  결론: case2에서는 남은 긴 numeric-phrase 한 줄을 더 자르는 방향도 채택하지 않는다. 다음 실험은 survivor row 제거가 아니라 다른 runtime overhead 또는 no-UI observability 쪽으로 옮긴다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_053424_466325_49221/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_053424_299395_49222/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_053450_377153_49855/benchmark_results.json`

- `apple_case2_pure_numeric_precision_skip`: case2 timing preset에서 Whisper primary의 pure numeric low-score row(`17.8`, `11.4`)를 word precision candidate에서 빼 runtime을 더 줄여보는 방향
  결과: one-shot에서는 `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_054417_977698_65778/benchmark_results.json` 기준 `elapsed_sec=20.290`, `quality_score=85.149`, `timing_priority_quality_score=85.483`, `timing_mae_sec=0.4076`였고, repeat 2x에서도 `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_054417_845607_65779/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_054439_865279_66581/benchmark_results.json` 기준 `elapsed_mean=19.306`, `spread=2.164`로 current accepted case2 band(`one-shot=15.503`, `repeat mean=15.233`)보다 명확히 나빴다.
  품질: `artifact_applied_word_precision_rows`는 `3 -> 2`로 줄었고 `17.8` precision은 실제로 빠졌지만, quality/timing이 소폭 내려가고 runtime은 오히려 크게 악화됐다.
  결론: case2에서는 pure numeric precision candidate를 줄이는 방향도 채택하지 않는다. 다음 실험은 precision candidate 제거가 아니라 다른 runtime overhead 또는 no-UI observability 쪽으로 옮긴다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_054417_977698_65778/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_054417_845607_65779/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_054439_865279_66581/benchmark_results.json`

- `apple_case1_terminal_punctuation_clause_split`: case1 timing preset에서 trailing period가 붙은 Apple STT1 raw row도 clause split 대상으로 허용해 raw segment count를 `6 -> 7`로 늘려보는 방향
  결과: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_060317_581646_94100/benchmark_results.json` 기준 `elapsed_sec=9.154`, `quality_score=63.855`, `timing_priority_quality_score=65.663`, `timing_mae_sec=0.7249`로 current accepted case1(`elapsed=2.144`, `quality=64.861`, `timing_priority_quality=67.113`, `timing_mae=0.6137`)보다 명확히 나빴다.
  품질: 첫 raw row가 `지금 에코프로를 놓은 상태고` / `크루즈 컨트롤 걸어볼게요.`로 쪼개지면서 `artifact_primary_recheck_plan_counts`가 다시 `low_score=2`, `merged=2`, `ranges=2`로 생겼고, early `80km/h` gap도 그대로 남았다. 즉 row count만 늘고 alignment는 개선되지 않았다.
  결론: trailing punctuation clause split은 case1에서 row 개수는 늘려도 accepted timing/quality band를 깨므로 채택하지 않는다. 다음 case1 실험은 clause split이 아니라 `artifact_reference_gap_rows`로 보이는 alignment gap을 직접 겨냥해야 한다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_060317_581646_94100/benchmark_results.json`

- `apple_case1_preserve_all_common_split_rows_before_raw_restore`: case1 timing preset에서 `no-LLM raw-text restore`의 첫 분기에서도 common-split row를 raw text로 되감지 않게 해 split 결과를 더 오래 살리는 방향
  결과: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_061612_339361_10829/benchmark_results.json` 기준 `elapsed_sec=1.689`로 빨라 보였지만 `quality_score=58.544`, `timing_priority_quality_score=60.744`, `timing_mae_sec=0.7285`로 current accepted case1(`elapsed=1.537`, `quality=64.861`, `timing_priority_quality=67.113`, `timing_mae=0.6137`)보다 명확히 나빴다.
  품질: output row 수가 `6 -> 15`로 늘면서 `놓은 상태고 크루즈 컨트롤`, `걸어볼게요`, `컨트롤 걸었구요`, `계속 17.8`, `인데 너무`처럼 중간 split 조각이 살아났지만, 동시에 `80으로 크루즈 컨트롤 걸었구요.`, `순간 연비가 계속 17.8 인데 너무 안 바뀌는데.` 같은 긴 raw row도 같이 남아 중복/겹침이 생겼다. `artifact_reference_gap_rows`는 줄었지만 `artifact_output_gap_rows`와 전체 timing/quality는 오히려 나빠졌다.
  결론: common-split row를 raw restore 이전부터 전부 살리는 broad guard는 case1 alignment를 개선하지 못하고 중복 split row를 만든다. 이 방향은 채택하지 않고 즉시 되돌린다. 다음 시도는 broad preserve가 아니라 `split_index`/survivor shape를 더 좁게 보는 쪽이어야 한다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_061612_339361_10829/benchmark_results.json`

- `apple_case1_disable_post_integrity_raw_restore`: case1 timing preset에서 마지막 `no-LLM raw-text restore` 한 번만 끄면 final integrity 뒤 common-split chunk가 더 살아남을지 보는 방향
  결과: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_062205_125545_20105/benchmark_results.json` 기준 `elapsed_sec=2.113`, `quality_score=64.861`, `timing_priority_quality_score=67.113`, `timing_mae_sec=0.6137`이었다. quality/timing은 accepted case1과 완전히 같았고, output/reference gap과 `artifact_common_split_rows`도 사실상 동일했으며 runtime만 accepted case1 one-shot(`elapsed=1.537`)보다 나빠졌다.
  품질: `artifact_output_rows`가 여전히 6줄이고 각 줄이 계속 `split_index=0`인 채 남아서, final `post-integrity raw restore`는 current case1 collapse의 주원인이 아니었다. 즉 이 경계를 꺼도 `80km/h`, `178`, `tail mismatch` alignment gap은 그대로였다.
  결론: case1에서 마지막 raw restore를 끄는 방향은 no-op에 가깝고 accepted band보다 runtime만 악화시킨다. 이 실험은 채택하지 않고 되돌린다. 다음 실험은 `raw restore`가 아니라, 그보다 앞에서 `split_index=0`만 survivor가 되는 alignment/timing allocation owner를 직접 겨냥해야 한다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_062205_125545_20105/benchmark_results.json`

- `apple_case1_preserve_common_split_rows_in_first_raw_restore_pass`: case1 timing preset에서 `no-LLM raw-text restore`의 첫 분기에서도 common-split row를 raw text로 되감지 않게 해 split 결과를 더 오래 살리는 방향
  결과: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_065524_836202_83563/benchmark_results.json` 기준 `elapsed_sec=1.689`로 빨라 보였지만 `quality_score=58.544`, `timing_priority_quality_score=60.744`, `timing_mae_sec=0.7285`로 current accepted case1(`quality_score=64.861`, `timing_priority_quality_score=67.113`, `timing_mae_sec=0.6137`)보다 명확히 나빴다.
  품질: output row 수가 `6 -> 15`로 늘면서 `놓은 상태고 크루즈 컨트롤`, `걸어볼게요`, `컨트롤 걸었구요`, `계속 17.8` 같은 중간 split 조각이 살아났지만 동시에 긴 raw row도 같이 남아 중복과 겹침이 커졌다.
  결론: broad first-pass preserve는 case1 alignment를 개선하지 못하고 split duplication만 키운다. trace tooling은 유지하되, 이 rule 자체는 채택하지 않고 즉시 되돌린다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_065524_836202_83563/benchmark_results.json`

- `apple_case1_preserve_numeric_singleton_nonzero_split_rows`: case1 timing preset에서 `first raw_restore` 대상 중 `non-zero split + 숫자 1토큰`만 살려보는 아주 좁은 additive 실험
  결과: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_071216_221851_18543/benchmark_results.json` 기준 `elapsed_sec=1.441`로 빨라 보였지만 `quality_score=58.544`, `timing_priority_quality_score=60.744`, `timing_mae_sec=0.7285`로 current accepted case1(`quality_score=64.861`, `timing_priority_quality_score=67.113`, `timing_mae_sec=0.6137`)보다 크게 나빴다.
  품질: `11.4` singleton만 살렸는데도 `source_integrity` 단계에서 split row가 다시 넓게 살아나면서 output이 `지금 에코프로를 / 놓은 상태고 크루즈 컨트롤 / 걸어볼게요 / ... / 11.4 점`처럼 과분할/중복 상태로 무너졌다. 결과적으로 broad preserve 실험과 사실상 같은 회귀 패턴을 다시 밟았다.
  결론: `first raw_restore`는 숫자 singleton처럼 아주 좁은 subset만 살려도 downstream duplication이 다시 폭발한다. 이 방향은 채택하지 않고 즉시 되돌린다. 다음 실험은 preserve rule이 아니라 `raw_text_mismatch` 대상 자체를 바꾸거나, split row용 별도 raw-text source를 주는 방향이어야 한다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_071216_221851_18543/benchmark_results.json`

- `apple_case1_split_local_raw_text_for_numeric_singleton_rows`: case1 timing preset에서 common-split row가 부모 full-anchor raw text 대신 split-local raw text를 들고 가게 해서 `17.8에서 11.4 점` all-singleton restore group만 source-level로 좁혀보는 실험
  결과: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_072042_926991_30324/benchmark_results.json` 기준 `elapsed_sec=1.557`, `quality_score=58.544`, `timing_priority_quality_score=60.744`, `timing_mae_sec=0.7285`로 current accepted case1(`elapsed=1.537`, `quality=64.861`, `timing_priority_quality=67.113`, `timing_mae=0.6137`)보다 명확히 나빴다.
  품질: tail group의 raw restore는 실제로 줄었지만 output이 다시 `11.4 점`, `순간 연비가 계속 17.8 인데 너무 안 바뀌는데.`, `컨트롤 걸었구요` 같은 중복/과분할 구조로 무너졌다. 즉 `preserve` rule이 아니라 source-level local raw text로 좁혀도 downstream duplication 패턴은 그대로 재현됐다.
  결론: case1에서 `all-singleton numeric restore group`에 split-local raw text를 주는 방향도 채택하지 않는다. 다음 실험은 split-row raw text source 자체를 더 건드리기보다, current accepted diagnostics를 유지한 채 다른 owner 경계를 찾는 쪽으로 옮긴다.

- `apple_case1_tighter_common_split_9_14_2_4`: case1 timing preset의 공통 split guard를 `10/16/2.6`에서 `9/14/2.4`로 한 단계 더 타이트하게 만들어 under-segmentation을 줄여보는 benchmark-only 실험
  결과: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_073853_688827_64343/benchmark_results.json` 기준 `elapsed_sec=1.726`, `quality_score=64.861`, `timing_priority_quality_score=67.113`, `timing_mae_sec=0.6137`이었다. 즉 accepted case1과 점수는 완전히 같았지만 runtime만 `1.537 -> 1.726`으로 나빠졌다.
  품질: `artifact_common_split_rows`와 최종 output shape는 accepted case1과 사실상 동일했는데, `artifact_raw_restore_restore_groups=6`, `trim_recent_overlap_decisions.drop=11`, `final_cleanup_step_changes.trim_recent_overlap_rows=11`이 다시 살아나서 같은 결과를 더 비싸게 만든 상태였다.
  결론: case1 common-split guard를 더 타이트하게 조이는 방향은 current accepted band를 개선하지 못하고 raw-restore/trim work만 되살린다. 이 실험은 즉시 되돌리고, 다음 case1 실험은 split 숫자 자체보다 `raw_restore/gap` owner를 더 좁게 보는 쪽으로 유지한다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_072042_926991_30324/benchmark_results.json`

- `apple_case2_tight_precision_straggler_knobs`: case2 timing preset에서 precision worker straggler timeout/ratio/missing-chunk 한도를 더 공격적으로 조여 runtime만 줄여보는 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_072509_076525_34229/benchmark_results.json` 기준 `elapsed_sec=32.544`, repeat 2x는 `elapsed_mean=24.1475`, `spread=16.817`로 current accepted case2(`elapsed_sec=15.503`)보다 훨씬 느려졌다. quality/timing은 `85.164 / 85.498 / 0.4076`으로 그대로였다.
  품질: 기능 삭제 없이 precision/recheck 경계만 조였지만, 실제론 runtime variance와 worst-case elapsed가 크게 악화됐다. 더 타이트한 straggler 정책이 빠른 조기 종료가 아니라 느린 recovery/variance를 불러오는 경로로 보인다.
  결론: case2 runtime-only 최적화에서 precision straggler knob를 더 타이트하게 조이는 방향은 채택하지 않는다. 다음 runtime slice는 다른 overhead owner나 no-UI observability를 먼저 강화해야 한다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_072509_076525_34229/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_072509_072378_34230/benchmark_results.json`

- `apple_case1_force_final_integrity_fallback`: case1 timing preset에서 `subtitle_final_integrity_min_similarity=0.98`, `subtitle_final_integrity_max_length_delta_ratio=0.02`로 `final_transcript_integrity_guard`를 강제로 실패시켜 `source_stt_segments` fallback을 유도하는 실험
  결과: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_075150_302863_83588/benchmark_results.json` 기준 `elapsed_sec=1.595`, `quality_score=58.544`, `timing_priority_quality_score=60.744`, `timing_mae_sec=0.7285`로 current accepted case1(`64.861 / 67.113 / 0.6137`)보다 크게 나빴다.
  품질: fallback은 실제로 걸렸고 `artifact_final_transcript_integrity_policy.accepted=false`, `fallback=source_stt_segments`, `artifact_stt_anchor_guard_rows=1`이 확인됐다. 하지만 그 대가로 `common_split_output_count=14`, `missing_common_split_group_count=8`, `raw_restore_restore_group_count=6`까지 다시 살아나면서 broad split/raw-restore duplication 패턴이 재현됐다.
  결론: case1에서 integrity threshold를 더 엄격하게 만들어 source-integrity fallback을 강제하는 방향은 채택하지 않는다. 다음 case1 slice는 integrity forcing보다 pre-guard output shape owner를 계속 좁게 보는 것이 맞다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_075150_302863_83588/benchmark_results.json`

- `apple_case1_skip_all_phrase_digit_pair_rows`: case1 timing preset에서 `all-phrase + digit + split_count=2` common split group을 통째로 건너뛰어 `80km/h로 크루즈 컨트롤 걸었고요`, `17.8 유지가 되고 있구요` 같은 짧은 숫자-구문 split churn을 줄여보는 benchmark-only 실험
  결과: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_080641_195024_38236/benchmark_results.json` 기준 `elapsed_sec=2.994`, `quality_score=66.329`, `timing_priority_quality_score=68.824`, `timing_mae_sec=0.5201`로 current accepted case1(`elapsed=1.624`, `quality=66.468`, `timing_priority_quality=68.999`, `timing_mae=0.5061`)보다 전부 나빴다.
  품질: `artifact_common_split_rows`에서는 `80km/h로 크루즈 컨트롤 걸었구요`, `17.8 유지가 되고 있구요`가 `split`에서 `post_gap_duration_clamp`로 바뀌고, `missing_common_split_group_count`와 `raw_restore_restore_group_count`도 `5 -> 3`으로 줄었다. 하지만 이 reduction이 실제 timing/quality 개선으로 이어지지 않았고, 오히려 같은 owner를 더 비싸게 통과시키는 패턴이 됐다.
  결론: case1에서 `all-phrase digit pair` split group을 통째로 끄는 방향은 진단상 그럴듯해 보여도 실제론 wrong owner다. 현재 accepted case1은 `all-singleton digit skip only` 구성으로 유지하고, 다음 slice는 이 guard를 넓히지 말고 `raw_restore/gap` owner만 더 좁게 봐야 한다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_080641_195024_38236/benchmark_results.json`

- `apple_case1_skip_all_phrase_digit_long_rows`: case1 timing preset에서 `숫자 포함 + all-phrase + split_count>=4 + 긴 span` common split group을 통째로 건너뛰어 상위 gap-owner인 `순간 연비가 계속 17.8 인데 너무 안 바뀌는데`를 직접 줄여보는 benchmark-only 실험
  결과: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_081851_293998_98264/benchmark_results.json` 기준 `elapsed_sec=1.619`, `quality_score=65.809`, `timing_priority_quality_score=68.141`, `timing_mae_sec=0.5824`로 current accepted case1(`elapsed=1.624`, `quality=66.468`, `timing_priority_quality=68.999`, `timing_mae=0.5061`)보다 timing/quality가 분명히 나빠졌다.
  품질: `artifact_common_split_rows`에서 상위 gap-owner span `19.694 -> 26.432`는 `split`에서 `post_gap_duration_clamp`로 바뀌어 split churn은 줄었지만, `artifact_gap_owner_groups`는 여전히 `4`개였고 `178에서 연비가 안 바뀌는데` gap도 그대로 남았다. 즉 가장 큰 gap-owner를 직접 건드렸어도 점수 개선으로 이어지지 않았다.
  결론: case1에서 `all-phrase digit long-row`를 통째로 unsplit/clamp하는 방향도 wrong owner다. 상위 gap-owner를 줄이려면 split churn 자체가 아니라 그 span의 downstream alignment/timing allocation을 더 직접 겨냥해야 한다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_081851_293998_98264/benchmark_results.json`

- `apple_case1_preserve_long_digit_phrase_common_split_rows_in_first_raw_restore`: case1 timing preset에서 first `raw_restore` 단계에서만 `long + digit + phrase + split_count>=4` common-split row를 parent full-anchor text로 되돌리지 않는 benchmark-only 실험
  결과: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_082951_810581_31922/benchmark_results.json` 기준 `elapsed_sec=1.777`, `quality_score=58.544`, `timing_priority_quality_score=60.744`, `timing_mae_sec=0.7285`로 current accepted case1(`elapsed=1.624`, `quality=66.468`, `timing_priority_quality=68.999`, `timing_mae=0.5061`)보다 크게 나빠졌다.
  품질: top long span `순간 연비가 계속 17.8 인데 너무 안 바뀌는데`는 실제로 local split rows(`순간 연비가`, `계속 17.8`, `인데 너무`, `안 바뀌는데 17.8에서`)로 살아났지만, 그 대가로 `artifact_final_transcript_integrity_policy`가 `accepted=false`, `fallback=source_stt_segments`, `reason=source_preservation:number_changed`로 뒤집혔다. 동시에 `common_split_output_count=14`, `missing_common_split_group_count=8`, `raw_restore_restore_group_count=5`까지 다시 커져 broad split churn 패턴이 재현됐다.
  결론: first raw-restore 단계에서 long digit phrase split rows를 보존하는 방향도 wrong owner다. top span을 직접 건드려도 결국 integrity fallback과 broad split churn을 다시 불러온다. 다음 slice는 first raw-restore 이전/직후가 아니라 더 downstream alignment/timing allocation owner를 겨냥해야 한다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_082951_810581_31922/benchmark_results.json`

- `apple_case1_split_local_raw_text_for_long_digit_phrase_rows`: case1 timing preset에서 `digit + split_count>=4 + source_duration>=6.0s` common-split row만 parent full-anchor raw text 대신 split-local raw text를 들고 가게 해 top long-digit-phrase span(`순간 연비가 계속 17.8 인데 너무 안 바뀌는데`)만 source-level로 좁혀보는 benchmark-only 실험
  결과: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_084132_696260_62153/benchmark_results.json` 기준 `elapsed_sec=2.199`, `quality_score=58.544`, `timing_priority_quality_score=60.744`, `timing_mae_sec=0.7285`로 current accepted case1(`elapsed=1.624`, `quality=66.468`, `timing_priority_quality=68.999`, `timing_mae=0.5061`)보다 크게 나빠졌다.
  품질: top long-digit span은 실제로 `순간 연비가 / 계속 17.8 / 인데 너무 / 안 바뀌는데 17.8에서`처럼 local split rows로 살아났지만, 동시에 `artifact_final_transcript_integrity_policy`가 다시 `accepted=false`, `fallback=source_stt_segments`, `reason=source_preservation:number_changed`로 뒤집혔다. `common_split_output_count=14`, `missing_common_split_group_count=8`, `raw_restore_restore_group_count=4`가 다시 살아나면서 broad split churn/duplication 패턴도 재현됐다.
  결론: top long-digit-phrase span에 split-local raw text를 주는 source-level 실험도 wrong owner다. local raw text로 source를 더 좁혀도 결국 integrity fallback과 과분할이 다시 터진다. 다음 slice는 split-row raw text source를 더 만지지 말고, 이 span class의 downstream alignment/timing allocation owner를 직접 겨냥해야 한다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_084132_696260_62153/benchmark_results.json`

- `apple_case2_parallel_recheck_clip_prep`: `core/audio/stt_recheck_service.py collect_prepared_recheck_clips(...)`를 ThreadPool 기반으로 병렬화해서 clip preparation이 `secondary_low_score_recheck`나 `word_precision_recheck` 병목인지 확인하는 runtime-only 실험
  결과: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_091145_768042_18777/benchmark_results.json` 기준 `elapsed_sec=22.837`로 fresh trace baseline인 `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_090629_632760_10268/benchmark_results.json`의 `21.704`보다 느려졌다. quality/timing은 `85.164 / 85.498 / 0.4076`으로 그대로였다.
  품질: `compare-current-vs-accepted --accepted-json` 기준 `selective_runtime_total_ms_delta=+1120.29`였고, 세부 악화는 `primary_collect=+222.868`, `secondary_low_score_recheck=+362.263`, `word_precision_recheck=+535.175`였다. 즉 serial clip preparation이 current owner가 아니라는 뜻이다.
  결론: clip-prep parallelism은 current case2 trace-rich flow에서 도움이 안 되고 오히려 런타임만 악화시킨다. 다음 runtime-only slice는 `clip prep`이 아니라 `word_precision_recheck` 내부 owner를 더 직접 봐야 한다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_091145_768042_18777/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_090629_632760_10268/benchmark_results.json`

- `apple_case2_reduce_precision_workers_to_two`: `apple_case2_high_selective_timing_priority`에서 `stt_whisperkit_word_timestamp_concurrent_workers`를 `3 -> 2`로 낮추고 max worker도 맞춰서 `word_precision_recheck` wallclock을 줄여보는 runtime-only 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_091616_575353_27536/benchmark_results.json`은 좋아 보였지만, repeat 2x는 `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_091831_071256_29840/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_091900_870901_30381/benchmark_results.json` 기준 `elapsed_mean=26.144`, `spread=5.942`로 fresh trace baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_090629_632760_10268/benchmark_results.json`의 `21.704`보다 명확히 나빴다.
  품질: quality/timing은 `85.164 / 85.498 / 0.4076`으로 그대로였지만, variance가 커지고 repeat 평균이 후퇴했다. 즉 one-shot win이 stable improvement가 아니었다.
  결론: case2 precision worker cap reduction은 accept하지 않는다. current code는 원래 설정으로 되돌리고, 다음 runtime-only slice는 worker count 자체보다 `word_precision_recheck` 내부 owner를 더 직접 봐야 한다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_091616_575353_27536/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_091831_071256_29840/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_091900_870901_30381/benchmark_results.json`

- `apple_case2_precision_only_padding_015`: case2 timing preset에서 low-score rescue는 그대로 두고, word-precision clip padding만 `0.20 -> 0.15`로 줄여 precision collect runtime만 낮춰보는 runtime-only 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_094908_700238_18418/benchmark_results.json`은 `quality_score=85.171`, `timing_priority_quality_score=85.513`, `timing_mae_sec=0.4046`으로 소폭 좋아졌지만, repeat 2x는 `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_094945_344144_19574/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_095005_012118_20094/benchmark_results.json` 기준 `elapsed_mean=16.613`, `spread=3.33`으로 fresh trace baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_094018_374344_92748/benchmark_results.json`의 `14.879`보다 나빴다.
  품질: clip shape는 `word_precision_total_clip_duration_sec 24.08 -> 23.23`, `max 3.4 -> 3.3`으로 줄었지만, 동시에 `precision_candidate_count 6 -> 7`, `precision_applied_count 3 -> 2`, `recheck_range_count 2 -> 3`으로 upstream candidate shape가 악화됐다. fresh-baseline compare에서도 `major_runtime_total_ms_delta=+960.678`, `selective_runtime_total_ms_delta=+975.281`, `word_precision_runtime_total_ms_delta=+92.355`였다.
  결론: precision-only padding reduction은 one-shot 점수 개선이 있어도 repeat runtime을 망치므로 accept하지 않는다. current code는 separate precision padding knob를 유지하지 않고 원래 설정으로 되돌린다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_094908_700238_18418/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_094945_344144_19574/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_095005_012118_20094/benchmark_results.json`

- `apple_case2_skip_precision_for_secondary_rechecked_digit_phrases`: case2 timing preset에서 selective secondary recheck로 이미 확인한 metadata-only digit phrase를 word precision 후보에서 빼 runtime을 줄여보는 benchmark-only 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_100026_837565_34631/benchmark_results.json` 기준 `elapsed_sec=12.632`로 빨라졌지만, `quality_score=85.001`, `timing_priority_quality_score=85.303`, `timing_mae_sec=0.42`로 fresh trace baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_094018_374344_92748/benchmark_results.json`의 `85.164 / 85.498 / 0.4076`보다 나빠졌다.
  품질: `precision_candidate_count 6 -> 4`, `precision_applied_count 3 -> 1`, `word_precision_runtime_total_ms 6550.675 -> 3612.631`으로 precision cost는 크게 줄었지만, 동시에 `recheck_range_count 2 -> 4`, `secondary_low_score_recheck 1142.126 -> 1554.532`로 upstream burden이 커졌다. 결국 precision을 너무 많이 덜어내면서 quality/timing을 잃었다.
  결론: case2에서 `secondary recheck considered digit phrase` precision skip은 wallclock만 빠르게 만들고 score를 깎으므로 accept하지 않는다. current code는 이 guard를 유지하지 않고 원래 설정으로 되돌린다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_100026_837565_34631/benchmark_results.json`

- `apple_case2_skip_lowest_vad_nondigit_precision_row`: case2 timing preset에서 Whisper primary + metadata-only low-score + non-digit + `duration<=3.1s` + `vad_alignment_score<=50` precision 후보를 건너뛰는 benchmark-only 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_103252_590379_355/benchmark_results.json`은 `elapsed_sec=14.811`, `quality_score=85.164`, `timing_priority_quality_score=85.498`, `timing_mae_sec=0.4076`로 좋아 보였지만, repeat `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_103315_495405_1369/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_103334_558764_1875/benchmark_results.json` aggregate는 `elapsed_mean=16.0765`, `spread=3.781`로 fresh trace baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_101402_731386_70265/benchmark_results.json`의 `15.381`보다 나빴다.
  품질: shape는 실제로 줄었다. `precision_candidate_count 6 -> 5`, `word_precision_clip_count 9 -> 8`, `word_precision_non_applied_clip_duration_sec 17.26 -> 13.86`, `word_precision_collect_segments_ms 6239.313 -> 5740.26`이었지만, repeat runtime 안정성이 부족해서 accept할 수 없다.
  결론: `변화가 없네` 같은 lowest-VAD nondigit precision row 하나만 건너뛰는 좁은 guard도 stable runtime win이 아니다. current code는 이 guard를 유지하지 않고 원래 설정으로 되돌린다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_103252_590379_355/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_103315_495405_1369/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_103334_558764_1875/benchmark_results.json`

- `apple_case2_skip_overlapping_phrase_neighbor_pure_numeric_precision_row`: case2 timing preset에서 earlier pure-numeric metadata-only precision row를, 같은 normalized numeric text를 가진 overlapping later phrase precision row가 있을 때만 건너뛰는 benchmark-only 실험
  결과: intended target인 `11.4` non-applied precision clip은 실제로 빠졌다. one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_104824_546282_29836/benchmark_results.json` 기준 `word_precision_clip_count 8 -> 7`, `word_precision_non_applied_clip_count 5 -> 4`, `word_precision_non_applied_clip_duration_sec 14.98 -> 12.44`로 줄었다. 하지만 runtime은 `elapsed_sec=29.89`로 크게 악화됐다. repeat 2x인 `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_104824_527865_29837/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_104855_897313_30366/benchmark_results.json` aggregate는 `elapsed_mean=21.588`, `spread=16.604`였다.
  품질: `quality_score=85.164`, `timing_priority_quality_score=85.498`, `timing_mae_sec=0.4076`은 유지됐지만, runtime 안정성이 current accepted case2 baseline보다 훨씬 나빠졌다. 한 run은 `13.286s`까지 내려갔지만 다른 run은 `29.89s`까지 튀었으므로 stable win이 아니다.
  결론: overlapping later phrase가 있다고 earlier pure-numeric precision row를 더 줄이는 방향도 current case2에서는 accept하지 않는다. clip 수는 줄어도 collect/transcribe variance가 너무 커져서 current code에는 남기지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_104824_546282_29836/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_104824_527865_29837/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_104855_897313_30366/benchmark_results.json`

- `apple_case2_skip_flanked_nondigit_precision_row`: case2 timing preset에서 metadata-only non-digit precision row를, 앞뒤에 같은 normalized numeric text를 가진 pure-numeric Whisper row가 매우 가깝게 있을 때만 건너뛰는 benchmark-only 실험
  결과: intended target인 `유지가 되고 있고요` non-applied precision workload은 실제로 빠졌다. one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_105401_508807_35699/benchmark_results.json` 기준 `word_precision_clip_count 8 -> 7`, `word_precision_non_applied_clip_count 5 -> 4`, `word_precision_non_applied_clip_duration_sec 14.98 -> 11.6`으로 줄었다. 하지만 runtime은 `elapsed_sec=31.549`로 크게 악화됐다. repeat 2x인 `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_105401_529857_35698/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_105432_698609_36218/benchmark_results.json` aggregate는 `elapsed_mean=25.956`, `spread=11.198`이었다.
  품질: `quality_score=85.164`, `timing_priority_quality_score=85.498`, `timing_mae_sec=0.4076`은 유지됐지만, runtime 안정성은 current accepted case2 baseline보다 훨씬 나빠졌다.
  결론: flanked-nondigit metadata-only precision row를 줄이는 방향도 current case2에서는 accept하지 않는다. non-applied clip 수는 줄어도 collect/transcribe variance가 더 악화돼 current code에는 남기지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_105401_508807_35699/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_105401_529857_35698/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_105432_698609_36218/benchmark_results.json`

- `apple_case2_same_chunk_precision_collect_batching`: case2 timing preset에서 같은 source chunk 안의 인접 precision collect clip을 배치로 합쳐 repeated collect/transcribe work를 줄여보는 additive runtime-only 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_111941_570338_53340/benchmark_results.json` 기준 `elapsed_sec=12.808`로 빨라졌지만 `quality_score=84.951`, `timing_priority_quality_score=85.249`, `timing_mae_sec=0.4215`로 current accepted case2(`85.164 / 85.498 / 0.4076`)보다 바로 나빠졌다.
  품질: same-chunk batching은 collect/transcribe wallclock만 줄인 것이 아니라 final precision application shape도 바꿨다. `precision_applied_count`가 accepted band의 `3`에서 `1`로 줄었고, 결과적으로 quality/timing이 즉시 깨졌다.
  결론: same-chunk adjacent precision batching은 current case2에서 safe runtime-only owner가 아니다. batching hook과 preset gate는 즉시 원복하고, 다음 slice는 candidate shape를 덜 흔드는 다른 collect workload owner를 봐야 한다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_111941_570338_53340/benchmark_results.json`

- `apple_case2_skip_long_numeric_phrase_metadata_only_precision_row`: case2 timing preset에서 Whisper-primary `metadata-only + digit phrase + high-VAD + duration>=2.8s` precision row, 즉 `17.8에서 연비가 안 바뀌는데` class만 빼서 collect/transcribe workload를 줄여보는 benchmark-only 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_113117_517067_74228/benchmark_results.json`은 `elapsed_sec=14.153`, quality/timing unchanged로 좋아 보였고, 첫 repeat `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_113145_518974_74546/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_113159_855731_74690/benchmark_results.json` aggregate도 `elapsed_mean=13.2425`, `spread=0.031`로 좋아 보였다. 하지만 fresh re-repeat인 `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_113417_421225_77508/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_113439_921087_77684/benchmark_results.json` aggregate가 `elapsed_mean=23.8595`, `spread=7.217`로 붕괴했다.
  품질: 점수 자체는 전 구간에서 `quality_score=85.164`, `timing_priority_quality_score=85.498`, `timing_mae_sec=0.4076`으로 유지됐지만, runtime-only tuning으로서는 repeat stability가 전혀 확보되지 않았다. precision shape도 `clip_count 8 -> 7`, `non_applied_duration 14.98 -> 11.58`, `collect_segments_ms 5662.474 -> 4915.193`까지는 줄었지만, 그 shape 축소가 stable wallclock win으로 이어지지 않았다.
  결론: long numeric-phrase metadata-only precision skip은 accept하지 않는다. lucky fast run이 있더라도 fresh repeat가 current accepted case2 band보다 훨씬 나빠져서, current code에는 남기지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_113117_517067_74228/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_113145_518974_74546/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_113159_855731_74690/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_113417_421225_77508/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_113439_921087_77684/benchmark_results.json`

- `apple_case2_skip_short_numeric_phrase_between_same_numeric_neighbors`: case2 timing preset에서 Whisper-primary `metadata-only + short numeric phrase + high-VAD` precision row를, 같은 normalized numeric text를 가진 earlier pure-numeric row와 later numeric-phrase row가 둘 다 있을 때만 빼서 `계속 17.8인데` class를 제거해보는 benchmark-only 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_114158_583980_88847/benchmark_results.json` 기준 intended class는 실제로 빠졌다. `word_precision_clip_count 8 -> 7`, `word_precision_non_applied_clip_count 5 -> 4`, `word_precision_non_applied_clip_duration_sec 14.98 -> 12.72`로 줄었지만, elapsed는 fresh pre-experiment baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_113858_032866_85374/benchmark_results.json`의 `19.579`보다 나쁜 `21.078`이었다.
  품질: quality/timing은 `85.164 / 85.498 / 0.4076`으로 그대로였지만, runtime은 개선이 아니라 악화였다. compare 기준으로 `major_runtime_total_ms +1499.161`, `primary_collect +764.418`, `secondary_low_score_recheck +759.709`, `word_precision_recheck -88.672`라서 precision clip 하나를 줄인 이득이 다른 selective phase 악화로 상쇄됐다.
  결론: `계속 17.8인데` class 제거도 safe runtime-only win이 아니다. precision collect workload는 줄어도 전체 selective runtime이 나빠져서 current code에는 남기지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_114158_583980_88847/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_113858_032866_85374/benchmark_results.json`

- `apple_case2_collect_merge_single_heaviest_overlap_cluster`: case2 timing preset에서 word-precision apply range는 그대로 두고 collect WAV만 줄이기 위해, 가장 무거운 overlap cluster `22.06 -> 30.0` (`17.8에서 연비가 안 바뀌는데 / 11.4 / 11.4에서 또 안 바뀌네`)를 collect 단계에서만 하나로 합치는 additive runtime-only 실험
  결과: collect shape는 실제로 줄었다. `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_121904_650380_30789/benchmark_results.json` 기준 `word_precision_clip_count=8`, `word_precision_collect_clip_count=6`, merged collect row는 `merged_clip_count=3`, `collected_total_duration_sec=5.02`였다. 하지만 one-shot 결과가 `elapsed_sec=29.129`, `quality_score=85.122`, `timing_priority_quality_score=85.448`, `timing_mae_sec=0.4107`로 current accepted case2 `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_104005_026621_11559/benchmark_results.json`의 `14.77 / 85.164 / 85.498 / 0.4076`보다 명확히 나빠졌다.
  품질: collect-only merge였지만 실제로는 safe wallclock reduction이 아니었다. `word_precision_runtime_total_ms=14896.06`, `collect_segments_ms=14493.776`, `major_runtime_total_ms=29133.84`로 runtime이 크게 악화됐고, final output에는 `artifact_output_gap_rows`로 `11.4` gap까지 새로 생겼다. 즉 heavy cluster batching/merge가 precision application shape와 timing quality를 간접적으로 흔들었다.
  결론: case2에서 heavy overlap cluster를 collect-only로 합치는 방향은 safe runtime-only owner가 아니다. collect WAV count는 줄어도 quality/timing과 wallclock이 동시에 깨지므로 current code에는 남기지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_121904_650380_30789/benchmark_results.json`

- `apple_case2_allow_critical_keep_warm_and_collect_reuse`: case2 timing preset에서 `pressure_stage=critical`이어도 STT persistent worker keep-warm과 collect-worker reuse를 허용해 current-code slowdown을 줄여보는 benchmark-only runtime 실험
  결과: baseline one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_122640_990495_37701/benchmark_results.json`은 `elapsed_sec=29.178`, quality/timing `85.164 / 85.498 / 0.4076`이었고, 로그에는 `메모리 critical: STT persistent worker 재사용 중단`이 찍혔다. override one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_122833_887489_38805/benchmark_results.json`은 `elapsed_sec=23.898`로 좋아 보였고 로그도 `macOS STT persistent worker 유지: 다음 STT 재사용`으로 바뀌었다. 하지만 repeat `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_122919_294830_39347/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_122919_306876_39348/benchmark_results.json` aggregate가 `elapsed_mean=33.3155`, `spread=0.049`로 baseline보다 오히려 나빠졌다.
  재평가: 위 두 repeat는 병렬 실행이라 accept/reject 근거로 쓰지 않았다. clean sequential repeat 1 `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_123258_203464_44503/benchmark_results.json`은 `elapsed_sec=20.38`로 다시 좋아 보였지만, clean sequential repeat 2 `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_123455_302552_46620/benchmark_results.json`은 `elapsed_sec=28.748`로 baseline slow band로 돌아갔다.
  품질: quality/timing은 전 구간에서 `85.164 / 85.498 / 0.4076`으로 유지됐지만, clean sequential band 자체가 안정적이지 않았다. lucky one-shot과 1회 clean repeat는 있었어도 second clean repeat에서 유지되지 못해 accept 기준을 충족하지 못했다.
  결론: critical-pressure에서도 강제로 STT worker를 warm/reuse하게 하는 방향은 current case2에서 safe runtime-only win이 아니다. current code에는 남기지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_122640_990495_37701/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_122833_887489_38805/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_123258_203464_44503/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_123455_302552_46620/benchmark_results.json`

- `apple_case2_precision_allow_critical_concurrency`: case2 timing preset에서 `pressure_stage=critical`이어도 `word_precision` pass만 WhisperKit concurrency를 `1`로 고정하지 않게 풀어, keep-warm은 그대로 두고 precision collect wallclock만 줄여보는 benchmark-only runtime 실험
  결과: fresh current-code baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_124756_740772_70093/benchmark_results.json`은 `elapsed_sec=28.157`, quality/timing `85.164 / 85.498 / 0.4076`이었다. one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_125328_350836_77340/benchmark_results.json`은 `elapsed_sec=23.068`로 좋아 보였고, 로그에도 `STT-단어정밀 WhisperKit ANE/GPU batch concurrency: 3 chunks`가 확인됐다. 하지만 clean sequential repeat `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_125419_133914_78890/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_125454_998658_79438/benchmark_results.json` aggregate가 `elapsed_mean=33.7935`, `spread=0.229`로 baseline보다도 훨씬 느려졌다.
  품질: quality/timing은 전 구간에서 `85.164 / 85.498 / 0.4076`으로 유지됐지만, runtime-only tuning으로서는 clean repeat가 완전히 실패했다. one-shot 개선은 false win이었다.
  결론: `critical keep-warm/reuse`와 별개로, `critical precision concurrency`만 푸는 방향도 current case2에서는 safe runtime-only win이 아니다. current code에는 남기지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_124756_740772_70093/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_125328_350836_77340/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_125419_133914_78890/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_125454_998658_79438/benchmark_results.json`

- `apple_case2_precision_collect_policy_warning_only`: case2 timing preset에서 `word precision collect` 경로에만 `warning-stage` resource policy를 주입해 `critical -> transient_child_worker` fallback 비용만 줄여보는 benchmark-only runtime 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_130948_006241_1368/benchmark_results.json` 기준 `elapsed_sec=28.331`, `quality_score=85.164`, `timing_priority_quality_score=85.498`, `timing_mae_sec=0.4076`이었다. fresh current-code baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_124756_740772_70093/benchmark_results.json`의 `28.157 / 85.164 / 85.498 / 0.4076`보다 이미 느려서 repeat까지 갈 가치가 없었다.
  품질: 가설 자체는 실제로 적용됐다. runtime trace에서 `word_precision_collect_worker_source`가 baseline의 `transient_child_worker`에서 `cached_child_worker_reused`로 바뀌었고 `word_precision_collect_reuse_enabled=true`도 확인됐다. 하지만 그 상태에서도 `word_precision_runtime_total_ms=15274.332`, `collect_segments_ms=14943.237`, `major_runtime_total_ms=28333.946`로 baseline(`15139.103 / 14808.024 / 28162.411`)보다 더 나빠졌다.
  결론: current case2의 next owner는 `critical pressure collect policy` 자체가 아니라, 그 정책을 우회해도 남는 `collect workload`다. `word precision collect`에만 warning policy를 강제하는 방향도 safe runtime-only win이 아니므로 current code에는 남기지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_124756_740772_70093/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_130948_006241_1368/benchmark_results.json`

- `apple_case2_tight_duplicate_numeric_precision_padding`: case2 timing preset에서 heavy overlap cluster 안의 `duplicate pure-numeric + later longer phrase` precision row에만 tighter padding을 주어 collect burden만 줄여보는 benchmark-only runtime 실험
  결과: first run은 implementation mistake로 `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_131856_870033_11586/benchmark_results.json`에서 `cannot assign to field 'primary'`로 실패했고 즉시 고쳤다. fixed one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_131943_692538_13830/benchmark_results.json` 기준으로는 `elapsed_sec=31.283`, `quality_score=85.164`, `timing_priority_quality_score=85.498`, `timing_mae_sec=0.4076`이었다. fresh current-code baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_124756_740772_70093/benchmark_results.json`의 `28.157 / 85.164 / 85.498 / 0.4076`보다 훨씬 느려서 repeat까지 갈 가치가 없었다.
  품질: top heavy cluster `22.06 -> 30.0`의 burden은 실제로 아주 조금 줄었다. `non_applied_clip_duration_sec 5.94 -> 5.74`, `non_applied_collected_total_duration_sec 3.66 -> 3.56`이었지만, 동시에 `word_precision_runtime_total_ms 15139.103 -> 16606.049`, `collect_segments_ms 14808.024 -> 16207.853`로 크게 악화됐다. 즉 clip shape를 덜 흔들었어도 runtime은 오히려 나빠졌다.
  결론: duplicate pure-numeric row에 대한 local padding tightening도 safe runtime-only win이 아니다. heavy cluster의 collected burden을 몇 백 ms 줄이는 수준이 아니며, current code에는 남기지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_124756_740772_70093/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_131856_870033_11586/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_131943_692538_13830/benchmark_results.json`

- `apple_case2_tight_long_digit_phrase_precision_padding`: case2 timing preset에서 heavy overlap cluster의 `17.8에서 연비가 안 바뀌는데` 같은 `metadata-only + long digit phrase + high-VAD` precision row에만 tighter padding을 주어 collect burden을 줄여보는 benchmark-only runtime 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_133556_093860_43340/benchmark_results.json` 기준 `elapsed_sec=36.767`, `quality_score=85.164`, `timing_priority_quality_score=85.498`, `timing_mae_sec=0.4076`이었다. fresh current-code baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_124756_740772_70093/benchmark_results.json`의 `28.157 / 85.164 / 85.498 / 0.4076`보다 이미 훨씬 느려서 repeat까지 갈 가치가 없었다.
  품질: shape 축소는 아주 미미했다. compare 기준 `word_precision_non_applied_clip_duration_sec 14.98 -> 14.82`, `word_precision_non_applied_overlap_group_collected_duration_sec 3.66 -> 3.62` 수준이었지만, runtime은 `major_runtime_total_ms +8609.82`, `selective_runtime_total_ms +8379.326`, `word_precision_runtime_total_ms +5608.574`, 특히 `collect_segments_ms +5502.257`로 크게 악화됐다. 점수는 유지됐지만 runtime-only tuning으로서는 명백한 false optimization이었다.
  결론: long digit-phrase row에 대한 local padding tightening도 safe runtime-only win이 아니다. `11.4` pure-numeric flank와 마찬가지로, local padding만 만져서는 heavy cluster collect owner를 개선하지 못한다. current code에는 남기지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_124756_740772_70093/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_133556_093860_43340/benchmark_results.json`

- `apple_case2_word_precision_precollect_cleanup_under_critical_pressure`: case2 timing preset에서 word-precision collect 직전에만 `clear_audio_model_memory_caches(...)`를 한 번 실행해, critical-pressure 상태의 collect wallclock을 줄여보는 benchmark-only runtime 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_134157_217275_50568/benchmark_results.json` 기준 `elapsed_sec=34.645`, `quality_score=85.164`, `timing_priority_quality_score=85.498`, `timing_mae_sec=0.4076`이었다. fresh current-code baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_124756_740772_70093/benchmark_results.json`의 `28.157 / 85.164 / 85.498 / 0.4076`보다 이미 크게 느려서 repeat까지 갈 가치가 없었다.
  품질: score/timing은 그대로였지만, runtime-only tuning으로서는 wallclock이 약 `+6.49s` 악화됐다. 즉 collect shape를 건드리지 않는 memory-cleanup hook만으로는 current case2 slow band를 줄이지 못했다.
  결론: word-precision collect 직전 메모리 정리 토글은 safe runtime-only win이 아니다. 다음 owner는 cleanup/policy toggle이 아니라 heavy collect workload class 자체로 계속 좁혀야 한다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_124756_740772_70093/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_134157_217275_50568/benchmark_results.json`

- `apple_case2_word_precision_precollect_vad_release_under_critical_pressure`: case2 timing preset에서 word-precision collect 직전에만 `release_vad_runtime_models(...)`를 실행해, critical-pressure 상태의 collect wallclock을 줄여보는 benchmark-only runtime 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_135305_548623_64830/benchmark_results.json` 기준 `elapsed_sec=150.968`, `quality_score=85.164`, `timing_priority_quality_score=85.498`, `timing_mae_sec=0.4076`이었다. fresh current-code baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_124756_740772_70093/benchmark_results.json`의 `28.157 / 85.164 / 85.498 / 0.4076`보다 극단적으로 느려서 repeat까지 갈 가치가 없었다.
  품질: 점수는 그대로였지만 runtime은 완전히 붕괴했다. trace 기준 `major_runtime_total_ms 28162.411 -> 150972.272`, `primary_collect 9781.395 -> 129809.139`, `word_precision_runtime_total_ms 15139.103 -> 16834.767`, `collect_segments_ms 14808.024 -> 16351.686`이었다. `precollect_vad_release` 자체는 `77.717ms`로 작았지만, 그 뒤 wallclock이 크게 악화됐다.
  결론: VAD-only pre-release도 safe runtime-only win이 아니다. `precollect cleanup` family와 마찬가지로, collect 직전 cleanup/release 토글은 current case2 slow band의 다음 owner가 아니다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_124756_740772_70093/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_135305_548623_64830/benchmark_results.json`

- `apple_case2_precision_model_override_to_apple_speech`: case2 timing preset에서 word-precision pass만 `apple_speech:ko-KR`를 explicit precision model로 태워, heavy numeric cluster의 timing alignment나 collect cost를 개선해보는 benchmark-only 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_140001_221989_77236/benchmark_results.json` 기준 `elapsed_sec=20.991`, `quality_score=84.986`, `timing_priority_quality_score=85.288`, `timing_mae_sec=0.42`였다. fresh current-code baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_124756_740772_70093/benchmark_results.json`의 `28.157 / 85.164 / 85.498 / 0.4076`보다 runtime은 빨라 보였지만, quality/timing band가 바로 깨져서 repeat까지 갈 가치가 없었다.
  품질: runtime trace상 `word_precision_runtime_total_ms 15139.103 -> 4725.959`로 precision pass는 가벼워졌지만, 동시에 `word_precision_applied_count 3 -> 0`, `precision_candidate_count 6 -> 8`, `recheck_range_count 2 -> 4`로 shape가 무너졌다. 즉 더 싸게 돌았지만 실제 precision replacement를 거의 못 남겨 score/timing을 잃었다.
  결론: case2에서 Apple Speech를 precision model로 직접 태우는 family는 safe runtime-only win이 아니다. runtime 이득이 보여도 quality/timing 보호에 실패하므로 current code에는 남기지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_124756_740772_70093/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_140001_221989_77236/benchmark_results.json`

- `apple_case2_precision_model_override_to_whisperkit_turbo`: case2 timing preset에서 word-precision pass만 `whisperkit-persistent:large-v3-v20240930_turbo_632MB`를 explicit precision model로 태워, Apple precision-model override와는 다른 additive model route로 collect/transcribe cost를 줄여보는 benchmark-only 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_140354_174341_82708/benchmark_results.json` 기준 `elapsed_sec=84.946`, `quality_score=84.986`, `timing_priority_quality_score=85.288`, `timing_mae_sec=0.42`였다. fresh current-code baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_124756_740772_70093/benchmark_results.json`의 `28.157 / 85.164 / 85.498 / 0.4076`보다 runtime과 quality/timing이 모두 크게 나빠져 repeat까지 갈 가치가 없었다.
  품질: trace 기준 `precision_candidate_count 6 -> 8`, `precision_applied_count 3 -> 0`, `recheck_range_count 2 -> 4`로 shape가 무너졌고, 동시에 `major_runtime_total_ms 28162.411 -> 84950.819`, `word_precision_runtime_total_ms 15139.103 -> 70759.069`, `collect_segments_ms 14808.024 -> 70413.657`로 precision collect path 자체도 폭증했다. 즉 lighter explicit model route가 아니라 precision application collapse + collect blow-up이었다.
  결론: case2에서 explicit WhisperKit turbo precision-model override family도 waste다. `Apple precision-model override`와 마찬가지로, explicit precision model route를 강제로 바꾸는 방향은 current case2의 safe runtime-only owner가 아니다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_124756_740772_70093/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_140354_174341_82708/benchmark_results.json`

- `apple_case2_disable_duration_first_submission`: case2 timing preset에서 `stt_duration_first_submission_enabled`를 꺼서, single-source-chunk precision collect가 chronological submission에서 더 안정적으로 돌 수 있는지 보는 benchmark-only scheduling 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_141208_548709_94216/benchmark_results.json` 기준 `elapsed_sec=142.282`, `quality_score=85.164`, `timing_priority_quality_score=85.498`, `timing_mae_sec=0.4076`이었다. fresh current-code baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_124756_740772_70093/benchmark_results.json`의 `28.157 / 85.164 / 85.498 / 0.4076`보다 wallclock이 극단적으로 나빠져 repeat까지 갈 가치가 없었다.
  품질: quality/timing은 그대로였지만 runtime owner가 오히려 크게 붕괴했다. trace 기준 `major_runtime_total_ms 28162.411 -> 142286.884`, `primary_collect 9781.395 -> 118707.677`, `word_precision_runtime_total_ms 15139.103 -> 18973.631`, `collect_segments_ms 14808.024 -> 18401.311`이었다. 즉 `duration-first off`는 precision collect path 개선이 아니라 전체 transcribe scheduling을 악화시켰다.
  결론: current case2에서 `duration-first submission` scheduling family를 끄는 방향은 safe runtime-only owner가 아니다. current code에는 남기지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_124756_740772_70093/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_141208_548709_94216/benchmark_results.json`

- `apple_case2_same_source_chunk_precision_collect_reuse`: case2 timing preset에서 `word precision` prepared clip들을 개별 재전사하지 않고, 같은 source chunk transcript를 한 번만 재사용해 collect path를 줄여보는 benchmark-only 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_142315_535960_8809/benchmark_results.json` 기준 `elapsed_sec=148.214`, `quality_score=84.338`, `timing_priority_quality_score=84.538`, `timing_mae_sec=0.4592`였다. fresh current-code baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_124756_740772_70093/benchmark_results.json`의 `28.157 / 85.164 / 85.498 / 0.4076`보다 runtime과 quality/timing이 모두 크게 무너져 repeat까지 갈 가치가 없었다.
  품질: collect-path 가설 일부는 맞게 작동했다. `word_precision_collect_clip_count 0 -> 1`, `word_precision_runtime_total_ms 15139.103 -> 10970.532`, `collect_segments_ms 14808.024 -> 10580.88`로 precision collect subphase만 보면 줄었다. 하지만 동시에 `precision_applied_count 3 -> 2`, `word_precision_non_applied_clip_count 5 -> 6`, `primary_collect 9781.395 -> 133462.27`, `major_runtime_total_ms 28162.411 -> 148217.637`으로 전체 transcribe가 폭발했고, `artifact_output_gap_rows`에 `11.4`가 새로 드러났다.
  결론: same-source-chunk transcript reuse는 current case2에서 safe additive collect-path win이 아니다. `skip/padding/model/policy` family와는 다른 아이디어였지만, 현재 shape에서는 precision application과 전체 wallclock을 동시에 해친다. current code에는 남기지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_124756_740772_70093/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_142315_535960_8809/benchmark_results.json`

- `apple_case2_precision_disable_rescue_worker_options`: case2 timing preset에서 `word precision` pass만 `stt_rescue_whisper_mode`를 꺼서, rescue-oriented Whisper worker options 없이 collect path를 더 싸게 만들 수 있는지 보는 benchmark-only 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_143058_032556_15394/benchmark_results.json` 기준 `elapsed_sec=30.227`, `quality_score=85.164`, `timing_priority_quality_score=85.498`, `timing_mae_sec=0.4076`이었다. fresh current-code baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_124756_740772_70093/benchmark_results.json`의 `28.157 / 85.164 / 85.498 / 0.4076`보다 quality/timing은 같았지만 runtime이 느려서 repeat까지 갈 가치가 없었다.
  품질: precision collect owner를 직접 줄이려던 가설은 맞지 않았다. trace 기준 `major_runtime_total_ms 28162.411 -> 30230.73`, `primary_collect 9781.395 -> 10654.134`, `word_precision_runtime_total_ms 15139.103 -> 15987.969`, `collect_segments_ms 14808.024 -> 15619.523`로, precision pass와 primary collect가 같이 악화됐다. 즉 rescue worker options를 끄는 방향이 collect path를 가볍게 만들지 못했다.
  결론: current case2에서 `precision pass without rescue-whisper worker options` family도 safe runtime-only owner가 아니다. current code에는 남기지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_124756_740772_70093/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_143058_032556_15394/benchmark_results.json`

- `apple_case2_defer_long_metadata_only_digit_phrase_collect_submission`: case2 timing preset에서 `duration-first` collect ordering은 유지하되, top heavy cluster `22.06 -> 30.0`의 longest metadata-only digit-phrase precision clip만 뒤로 미뤄 `collect_segments` wallclock을 줄여보는 benchmark-only 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_145412_267911_72407/benchmark_results.json` 기준 `elapsed_sec=33.172`, `quality_score=85.164`, `timing_priority_quality_score=85.498`, `timing_mae_sec=0.4076`이었다. fresh pre-experiment baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_144519_903011_61332/benchmark_results.json`의 `31.227 / 85.164 / 85.498 / 0.4076`보다 runtime만 `+1.945s` 악화돼 repeat까지 갈 가치가 없었다.
  품질: quality/timing은 완전히 같았지만 runtime trace가 더 나빠졌다. `major_runtime_total_ms +1944.611`, `selective_runtime_total_ms +1587.831`, `word_precision_runtime_total_ms +521.731`, `collect_segments_ms +305.478`이었다. 더 중요한 점은 live no-UI check에서 top cluster submission order가 실제로 안 바뀌었다는 것이다. `17.8에서 연비가 안 바뀌는데`는 여전히 `submission_index=1`, `11.4`는 여전히 `submission_index=5`였다.
  결론: current case2에서 `long metadata-only digit-phrase collect defer` family는 safe runtime-only owner가 아니다. order hint가 live submission order를 유의미하게 바꾸지 못했고 runtime도 나빠졌으므로 current code에는 남기지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_144519_903011_61332/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_145412_267911_72407/benchmark_results.json`

- `apple_case2_prioritize_phrase_linked_pure_numeric_collect_submission`: case2 timing preset에서 overlapping longer phrase neighbor가 이미 있는 pure-numeric precision clip만 collect 우선순위를 올려 `11.4` heavy subclip의 submission index를 앞으로 당겨보는 benchmark-only ordering 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_150354_793978_85680/benchmark_results.json` 기준 `elapsed_sec=29.746`, `quality_score=85.164`, `timing_priority_quality_score=85.498`, `timing_mae_sec=0.4076`이었다. fresh pre-experiment baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_144519_903011_61332/benchmark_results.json`의 `31.227 / 85.164 / 85.498 / 0.4076`보다 one-shot runtime은 `-1.481s` 좋아 보였다.
  품질: score/timing은 그대로였고 runtime trace도 `major_runtime_total_ms -1482.057`, `word_precision_runtime_total_ms -1800.393`, `collect_segments_ms -1752.644`로 개선처럼 보였다. 하지만 핵심 owner evidence는 실패였다. live no-UI check에서 top cluster submission order가 실제로 안 바뀌었다. `17.8에서 연비가 안 바뀌는데`는 여전히 `submission_index=1`, `11.4`는 여전히 `submission_index=5`였다.
  결론: one-shot 수치가 좋아 보여도 intended owner인 collect ordering이 바뀌지 않았으므로 causal win으로 받아들이면 안 된다. current case2에서 `phrase-linked pure-numeric collect prioritization` family도 proof 없는 noise band로 보고 current code에는 남기지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_144519_903011_61332/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_150354_793978_85680/benchmark_results.json`

- `apple_case2_prioritize_short_digit_phrase_collect_submission`: case2 timing preset에서 기존 pure-numeric collect prioritization을 끄고, cluster-2 subclip `계속 17.8인데`에만 explicit duration-first prioritize offset을 줘서 collect order owner를 더 좁게 찌르는 benchmark-only ordering 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_152205_140929_97192/benchmark_results.json` 기준 `elapsed_sec=28.024`, `quality_score=85.164`, `timing_priority_quality_score=85.498`, `timing_mae_sec=0.4076`이었다. fresh pre-experiment baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_144519_903011_61332/benchmark_results.json`의 `31.227 / 85.164 / 85.498 / 0.4076`보다 one-shot runtime은 `-3.203s` 좋아 보였다.
  품질: quality/timing은 그대로였고 runtime trace도 `major_runtime_total_ms -3205.433`, `selective_runtime_total_ms -3100.444`, `word_precision_runtime_total_ms -2092.101`, `collect_segments_ms -2038.315`로 개선처럼 보였다. 하지만 compare proof는 여전히 `word_precision_submission_delta_rows=[]`, `word_precision_submission_index_changed_count=0`, `word_precision_submission_order_proven=false`였다. 즉 intended collect-order owner가 실제로는 하나도 움직이지 않았다.
  결론: this is another false win. runtime 수치가 좋아 보여도 `submission_index`가 바뀌지 않았으므로 causal improvement로 받으면 안 된다. current case2에서 `short digit-phrase collect prioritization` family도 proof 없는 noise band로 보고 current code에는 남기지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_144519_903011_61332/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_152205_140929_97192/benchmark_results.json`

- `apple_case2_revalidate_phrase_linked_pure_numeric_collect_prioritization_after_swift_fix`: swift duration-first offset fix 이후 `11.4` subclip을 다시 살려보는 benchmark-only 재검증 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_155842_230093_15980/benchmark_results.json` 기준 `elapsed_sec=29.162`, `quality_score=85.164`, `timing_priority_quality_score=85.498`, `timing_mae_sec=0.4076`이었다. fresh fast rerun baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_154144_634637_8513/benchmark_results.json`의 `21.862 / 85.164 / 85.498 / 0.4076`보다 runtime이 다시 나빠졌다.
  품질: 점수는 그대로였지만 compare proof가 여전히 실패했다. `word_precision_submission_index_changed_count=0`, `word_precision_submission_order_proven=false`였고, `11.4`는 여전히 `submission_index=6`, `17.8에서 연비가 안 바뀌는데`는 여전히 `submission_index=2`였다. trace도 `word_precision_runtime_total_ms_delta=+7037.101`, `major_runtime_total_ms_delta=+7300.214`로 악화됐다.
  결론: swift scheduler fix가 살아난 뒤에도, 이번 concrete `phrase-linked pure-numeric` revalidation implementation은 live collect order를 못 움직였다. 즉 이 implementation은 여전히 waste다. code/tests는 전부 원복했고 current code에는 남기지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_154144_634637_8513/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_155842_230093_15980/benchmark_results.json`

- `apple_case2_revalidate_long_metadata_only_digit_phrase_collect_defer_after_swift_fix`: swift duration-first offset fix 이후 `17.8에서 연비가 안 바뀌는데` long digit-phrase를 collect 뒤쪽으로 미뤄보는 benchmark-only 재검증 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_161027_441433_19812/benchmark_results.json` 기준 `elapsed_sec=27.399`, `quality_score=85.164`, `timing_priority_quality_score=85.498`, `timing_mae_sec=0.4076`이었다. fresh fast rerun baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_154144_634637_8513/benchmark_results.json`의 `21.862 / 85.164 / 85.498 / 0.4076`보다 runtime이 다시 나빠졌다.
  품질: 이번엔 causal proof 자체는 있었다. top cluster에서 `17.8에서 연비가 안 바뀌는데`가 `submission_index 2 -> 7`로 실제 뒤로 밀렸고, `11.4에서 또 안 바뀌네`는 `4 -> 3`, `11.4`는 `6 -> 5`로 당겨졌다. 하지만 그 결과가 runtime win으로 이어지지 않았고, trace도 `major_runtime_total_ms_delta=+5537.327`, `word_precision_runtime_total_ms_delta=+6151.033`로 악화됐다.
  결론: swift scheduler fix 이후 long-digit defer family는 이제 live submission order를 움직일 수는 있지만, current case2에서는 그 ordering move 자체가 runtime 개선을 보장하지 않는다. 이 concrete implementation은 waste로 기록하고 current code에는 남기지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_154144_634637_8513/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_161027_441433_19812/benchmark_results.json`

- `apple_case2_tight_precision_straggler_timeout`: case2 timing preset에서 `stt_word_timestamp_worker_straggler_timeout_sec`를 `10.0 -> 4.5`로만 줄여, 마지막 non-applied precision clip이 `word_precision collect` wallclock을 덜 막는지 보는 benchmark-only runtime 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_172833_771714_46041/benchmark_results.json` 기준 `elapsed_sec=28.865`, `quality_score=85.164`, `timing_priority_quality_score=85.498`, `timing_mae_sec=0.4076`이었다. fresh current-code latency baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_171442_661504_32528/benchmark_results.json`의 `14.644 / 85.164 / 85.498 / 0.4076`보다 runtime이 크게 나빠져 repeat까지 갈 가치가 없었다.
  품질: score/timing은 그대로였지만 runtime trace가 크게 악화됐다. compare 기준 `major_runtime_total_ms_delta=+14224.305`, `selective_runtime_total_ms_delta=+13881.914`, `word_precision_runtime_total_ms_delta=+9971.774`였고, 특히 `collect_segments_ms 5905.1 -> 15690.761`로 폭증했다. current one-shot에서는 collect state도 `warning + cached_child_worker_reused`가 아니라 `critical + transient_child_worker`로 밀려 있어, tighter straggler timeout이 safe runtime-only win을 만들지 못했다.
  결론: current case2에서 tighter precision straggler-timeout family는 waste다. non-applied tail clip을 더 빨리 포기해도 안정적 runtime 이득으로 이어지지 않았고, current code에는 남기지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_171442_661504_32528/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_172833_771714_46041/benchmark_results.json`

- `apple_case2_relax_compressed_memory_thresholds_for_precision_collect`: case2 timing preset에서만 native/Python compressed-memory warning/critical threshold를 높여, `word precision collect`를 `critical + transient_child_worker`에서 `warning + cached_child_worker_reused`로 내리는 benchmark-only runtime 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_175629_148603_78413/benchmark_results.json` 기준 `elapsed_sec=22.898`, `quality_score=85.164`, `timing_priority_quality_score=85.498`, `timing_mae_sec=0.4076`으로 좋아 보였다. compare vs fresh critical baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_174111_404723_62578/benchmark_results.json`에서는 실제로 `word_precision_collect_pressure_stage critical -> warning`, `worker_source transient_child_worker -> cached_child_worker_reused`, `word_precision_runtime_total_ms_delta=-6597.245`였다.
  품질: one-shot에서는 intended owner가 실제로 움직였다. 하지만 sequential repeat `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_175725_152949_78930/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_175725_115312_78931/benchmark_results.json`이 `elapsed_sec=34.904`, `35.021`로 느려졌고, aggregate `elapsed_mean=34.9625`, `spread=0.117`이었다. quality/timing은 그대로였지만 runtime은 fresh critical baseline `29.36`보다도 나빴다.
  결론: compressed-memory threshold relaxation은 owner를 바꾸는 causal effect는 있었지만 stable runtime win은 아니었다. current case2에서는 safe tuning으로 채택하지 않고, 관련 preset/test 변경은 원복한다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_174111_404723_62578/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_175629_148603_78413/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_175725_152949_78930/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_175725_115312_78931/benchmark_results.json`

- `apple_case2_precollect_native_allocator_pressure_relief`: case2 timing preset에서 accepted fresh-native-snapshot collect 직후, native allocator pressure relief를 한 번 더 태워 `critical/native/transient` collect state를 내려보려는 benchmark-only runtime 실험
  결과: one-shot `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_185719_676958_48871/benchmark_results.json` 기준 `elapsed_sec=26.916`, `quality_score=85.164`, `timing_priority_quality_score=85.498`, `timing_mae_sec=0.4076`이었다. 비교 기준 current-code baseline `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_184845_616058_37175/benchmark_results.json`의 `25.368 / 85.164 / 85.498 / 0.4076`보다 runtime만 `+1.548s` 악화돼 repeat까지 갈 가치가 없었다.
  품질: quality/timing은 그대로였지만 collect trace상 intended owner가 전혀 안 움직였다. `native_allocator_pressure_relief_requested=true`, `native_allocator_pressure_relief_ok=true`였지만 `native_allocator_pressure_relief_released_bytes=0`이었고, `pressure_stage_before_allocator_relief=critical` 이후 final collect state도 계속 `pressure_stage=critical`, `worker_source=transient_child_worker`였다.
  결론: current case2 native-pressure path에서는 allocator relief hook이 실제로 불필요 메모리를 풀지 못했고, runtime만 악화됐다. 이 family는 현 조건에서 waste로 잠그고 current code에는 남기지 않는다.
  artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_184845_616058_37175/benchmark_results.json`, `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_185719_676958_48871/benchmark_results.json`
# 2026-06-02 case2 primary_collect seed chunk profile tightening rejected

- scope:
  - `apple_case2_high_selective_timing_priority`에만 `audio_chunk_profile_sec=14.0`를 주는 bounded runtime-only 실험
  - 목적은 `primary_collect` 이전 seed chunk shape를 잘게 만들어 current `primary_collect_path` owner를 줄이는 것

- evidence:
  - artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_195007_445050_17366/benchmark_results.json`
  - result: `elapsed=26.678`, `quality=85.164`, `timing_priority_quality=85.498`, `timing_mae=0.4076`
  - compare baseline: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_184845_616058_37175/benchmark_results.json`
    - baseline `elapsed=25.368`, same quality/timing
  - critical observation:
    - experiment setting was present: `audio_chunk_profile_sec=14.0`
    - but seed chunk shape stayed the same: `audio_extracts[0].chunk_wavs=1`
    - runtime only regressed, so repeat 가치 없음

- why rejected:
  - intended owner was `seed chunk shape before primary_collect`, but the actual seed chunk count did not move
  - runtime got worse while quality/timing stayed flat, so this is a no-effect shape tweak plus regression

- do not retry:
  - do not reopen `audio_chunk_profile_sec` tightening alone as the next case2 primary_collect experiment
  - next `primary_collect_path` slice should target backend/routing path owners directly, not this seed-profile-only family

# 2026-06-02 case2 selective-secondary overlap precision skip rejected

- scope:
  - temporary case2-only runtime flag `stt_word_precision_skip_secondary_recheck_overlap_enabled`
  - intention was to skip `word precision` ranges already covered by `selective secondary recheck`
  - bounded experiment only on `apple_case2_high_selective_timing_priority`

- evidence:
  - artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_203924_532856_74885/benchmark_results.json`
  - result: `elapsed=176.104`, `quality=84.986`, `timing_priority_quality=85.288`, `timing_mae=0.42`
  - compare failed current artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_202913_365630_62299/benchmark_results.json`
    - prior failed run `elapsed=170.799`, same degraded quality/timing band
  - compare fast current artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_200911_806838_39625/benchmark_results.json`
    - fast current `elapsed=25.274`, `quality=85.164`, `timing_priority_quality=85.498`, `timing_mae=0.4076`
  - direct precision trace from the rejected run:
    - `range_count=8`
    - `prepared_clip_count=8`
    - `collect_segments_ms=70389.878`
    - `collected_segment_count=0`
  - prior failed precision trace was effectively the same:
    - `prepared_clip_count=8`
    - `collect_segments_ms=70376.172`
    - `collected_segment_count=0`

- why rejected:
  - intended owner was `duplicate precision collect caused by overlap with selective secondary recheck`
  - but the experiment did not reduce precision prepared clips at all, so the owner never moved
  - runtime remained in the same catastrophic timeout band and quality/timing stayed degraded

- do not retry:
  - do not reopen this `selective-secondary overlap precision skip` family
  - if precision collect is revisited, stay on non-skip owners that demonstrably change prepared clip shape or worker/runtime behavior in the live trace

# 2026-06-02 case2 exact native-policy MLX primary route rejected

- scope:
  - temporary case2-only variant `apple_case2_high_selective_timing_priority_mlx_primary_native_exact`
  - intention was to force the real `native_policy_selected_mlx_model` branch for the single-chunk `primary_collect` owner without touching UI/UX

- evidence:
  - artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_225839_539192_3558/benchmark_results.json`
  - result: `elapsed=70.004`, `quality=79.289`, `timing_priority_quality=80.056`, `timing_mae=0.4953`
  - compare baseline: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_200911_806838_39625/benchmark_results.json`
    - baseline `25.274 / 85.164 / 85.498 / 0.4076`
  - critical observation:
    - intended owner did move this time
    - selective trace `primary_collect` recorded:
      - `model=mlx-community/whisper-large-v3-mlx`
      - `elapsed_ms=8865.813`
      - `worker_source=cached_child_worker_created`
      - `pressure_stage=warning`
    - but total run still collapsed on the tail:
      - `word_precision_recheck elapsed_ms=58892.441`
      - final native summary `word_precision_count=0`
      - quality/timing dropped broadly

- why rejected:
  - this family proves that moving only the single-chunk `primary_collect` route into exact MLX is not enough for current case2
  - runtime remained far worse than the current fast baseline, and quality/timing also regressed
  - the remaining owner is downstream tail behavior, not this exact primary-route branch itself

- do not retry:
  - do not reopen `stt_native_exact_mlx_model_enabled` as the next case2 primary-route experiment
  - if case2 route work is revisited, treat this branch as already closed and move to the downstream non-skip precision tail owner instead

# 2026-06-02 case2 edge-safe alternate digit candidate fallback rejected

- scope:
  - temporary case2-only variant `apple_case2_high_selective_timing_priority_edge_safe_alternate`
  - intention was to keep the accepted current case2 fast path intact and only let `word precision` pick an edge-safe alternate candidate from the same numeric-core pool when the top candidate failed `candidate_edge_shift_exceeded`

- evidence:
  - artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_231855_226988_34846/benchmark_results.json`
  - result: `14.885 / 85.164 / 85.498 / 0.4076`
  - compare accepted fast case2 center:
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_230947_315695_18687/benchmark_results.json`
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_231025_598357_19241/benchmark_results.json`
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_231051_573560_19612/benchmark_results.json`
    - accepted repeat mean `14.195`, spread `0.119`
  - critical observation:
    - runtime regressed by about `+0.69s` against the accepted mean
    - quality/timing stayed flat
    - `word_precision_count` stayed `3`
    - precision collect worker/runtime shape stayed the same:
      - `worker_source=cached_child_worker_reused`
      - `pressure_stage=warning`
    - prepared clip shape for `계속 17.8인데`, `17.8에서 연비가 안 바뀌는데`, `11.4` did not change

- why rejected:
  - intended owner was the `precision apply gate` candidate selection itself
  - but live evidence did not show a new applied precision row or a changed prepared shape
  - the family only made runtime worse without moving the actual owner

- do not retry:
  - do not reopen `edge_safe_alternate_digit_candidate`
  - if `precision_apply_gate_edge_shift` is revisited, stay off broad threshold relaxation, numeric-core salvage, and this alternate-candidate branch

# 2026-06-02 case2 digit edge clipping inside precision gate rejected

- scope:
  - temporary case2-only variant `apple_case2_high_selective_timing_priority_digit_edge_clip`
  - intention was to keep the accepted current case2 fast path intact and only clip metadata-only digit phrase precision candidate timing inside the existing edge-shift gate instead of relaxing thresholds

- evidence:
  - artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_232518_318091_60723/benchmark_results.json`
  - result: `14.986 / 85.164 / 85.498 / 0.4076`
  - compare accepted fast case2 center:
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_230947_315695_18687/benchmark_results.json`
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_231025_598357_19241/benchmark_results.json`
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_231051_573560_19612/benchmark_results.json`
    - accepted repeat mean `14.195`, spread `0.119`
  - critical observation:
    - runtime regressed by about `+0.791s` against the accepted mean
    - quality/timing stayed flat
    - `word_precision_count` stayed `3`
    - the intended edge-gate owner still did not visibly move

- why rejected:
  - intended owner was the precision apply-gate itself
  - but clipping the candidate timing inside the existing gate did not unlock a new applied precision row
  - the family only made runtime worse without improving quality/timing

- do not retry:
  - do not reopen `digit_edge_clip`
  - if `precision_apply_gate_edge_shift` is revisited, stay off broad threshold relaxation, numeric-core salvage, alternate-candidate fallback, and this digit-edge clipping branch
## 2026-06-02 case2 short digit phrase collect pad0 token guard

- hypothesis
  - the accepted `short_digit_phrase_collect_pad0` tuning may still be too broad because it also touches longer command-like rows such as `80으로 크루즈 컨트롤 걸었고요`; adding a `max_token_count=2` guard could keep the cluster_1 win while restoring the lost `80` precision row.
- change
  - temporarily added a token-count guard to the short-digit-phrase local collect-pad0 hook and benchmarked:
    - `apple_case2_high_selective_timing_priority_short_digit_phrase_collect_pad0_token2`
- evidence
  - artifact:
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_234511_115098_72919/benchmark_results.json`
  - result:
    - `13.962 / 85.164 / 85.498 / 0.4076`
  - compare target:
    - accepted short-digit-pad0 aggregate center:
      - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_233944_942736_70106/benchmark_results.json`
      - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_234014_004291_70374/benchmark_results.json`
      - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_234028_513005_70356/benchmark_results.json`
      - mean `14.079`
      - timing-priority quality `85.537`
      - timing MAE `0.4061`
- rejection reason
  - runtime stayed similar or slightly faster, but quality/timing fell back to the older band and lost the accepted improvement:
    - `quality_score 85.164`
    - `timing_priority_quality_score 85.498`
    - `timing_mae 0.4076`
  - do not replace the accepted broader `short_digit_phrase_collect_pad0` tuning with this token-guard variant.

# 2026-06-02 case2 prefix-tail split inside precision apply gate rejected

- hypothesis
  - the new top owner in the accepted fast case2 artifact was the `80으로 크루즈 컨트롤 걸었고요` row, where the collected candidate text stopped at `80으로 크루즈 컨트롤` and failed with `candidate_edge_shift_exceeded`
  - maybe splitting that row into a timed prefix plus a short fallback tail could salvage the apply gate without broad threshold relaxation

- change
  - temporarily added a benchmark-only `prefix_tail_split` branch to `apply_word_precision_segments(...)`
  - temporary variant:
    - `apple_case2_high_selective_timing_priority_prefix_tail_split`

- evidence
  - artifact:
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_235414_032245_78820/benchmark_results.json`
  - result:
    - `31.735 / 44.354 / 46.717 / 1.4897`
  - compare accepted fast case2 band:
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_233944_942736_70106/benchmark_results.json`
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_234014_004291_70374/benchmark_results.json`
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_234028_513005_70356/benchmark_results.json`
    - accepted aggregate:
      - `14.079 / 85.199 / 85.537 / 0.4061`

- rejection reason
  - the family collapsed into broad split churn instead of a narrow owner fix:
    - `final_segments 61`
    - `timing_priority_quality_score 46.717`
    - `timing_mae 1.4897`
    - `overlap_count 18`
  - `source_preservation:number_changed` rollback fired
  - this is not a viable apply-gate salvage branch for case2

- do not retry
  - do not reopen `prefix_tail_split`
  - stay off broad split-like salvage for the `80...` row unless a future owner can prove no segment-count churn

# 2026-06-03 case2 longer digit phrase collect padding restore rejected

- hypothesis
  - the accepted `short_digit_phrase_collect_pad0` tuning may have helped `계속 17.8인데` while hurting the `80으로 크루즈 컨트롤 걸었고요` row by removing too much collect padding
  - maybe restoring only the longer high-VAD digit phrase padding to `0.2s` would improve the `80...` collect path without losing the accepted fast band

- change
  - temporarily added a benchmark-only `longer_digit_phrase_collect_padding` hook after the accepted short-digit pad0 reduction
  - temporary variant:
    - `apple_case2_high_selective_timing_priority_short_digit_phrase_collect_pad0_longer_digit_pad_restore`

- evidence
  - artifact:
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260603_000014_497832_82289/benchmark_results.json`
  - result:
    - `31.48 / 44.682 / 47.034 / 1.4934`
  - compare accepted fast case2 band:
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_233944_942736_70106/benchmark_results.json`
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_234014_004291_70374/benchmark_results.json`
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_234028_513005_70356/benchmark_results.json`
    - accepted aggregate:
      - `14.079 / 85.199 / 85.537 / 0.4061`

- rejection reason
  - this family regressed into the same broad churn shape as the rejected `prefix_tail_split` branch:
    - `final_segments 60`
    - `timing_priority_quality_score 47.034`
    - `timing_mae 1.4934`
    - `overlap_count 18`
  - `source_preservation:number_changed` rollback fired again
  - this is not a viable collect-path owner for the `80...` row

- do not retry
  - do not reopen `longer_digit_phrase_collect_padding_restore`
  - keep both `prefix_tail_split` and this collect-padding restore family hard-locked for `80으로 크루즈 컨트롤 걸었고요`

# 2026-06-03 case2 combined short-digit and low-vad collect-pad0 rejected

- hypothesis
  - the accepted current fast `case2` winner already benefited from `short_digit_phrase_collect_pad0`
  - maybe composing the separately accepted `low_vad_nondigit_collect_pad0` on top of it would reduce the remaining low-yield collect tail without losing the better timing band

- change
  - temporarily added a benchmark-only combined variant:
    - `apple_case2_high_selective_timing_priority_short_digit_phrase_collect_pad0_low_vad_nondigit_collect_pad0`

- evidence
  - artifact:
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260603_001310_681739_92584/benchmark_results.json`
  - result:
    - `32.618 / 44.696 / 47.051 / 1.4925`
  - compare accepted fast case2 band:
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_233944_942736_70106/benchmark_results.json`
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_234014_004291_70374/benchmark_results.json`
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_234028_513005_70356/benchmark_results.json`
    - accepted aggregate:
      - `14.079 / 85.199 / 85.537 / 0.4061`

- rejection reason
  - this was not an additive win; it collapsed into broad split/overlap churn:
    - `raw_segments 47`
    - `final_segments 60`
    - `word_precision_count 1`
    - `overlap_count 18`
  - `source_preservation:number_changed` rollback fired again
  - individually accepted local collect-pad tunings are not automatically safe when stacked on the current fast `case2` winner

- do not retry
  - do not reopen the combined `short_digit_phrase_collect_pad0 + low_vad_nondigit_collect_pad0` family

# 2026-06-03 case2 precise recheck filter on fast short-digit winner rejected

- hypothesis
  - current fast `case2` winner still had non-applied collect-path rows where the collected text collapsed to the first word only
  - maybe the native fast recheck audio filter was too aggressive, and switching recheck/precision trim back to the broader speech-focused filter would improve collect-path output without losing the accepted fast band

- change
  - temporarily added a benchmark-only variant:
    - `apple_case2_high_selective_timing_priority_short_digit_phrase_collect_pad0_precise_recheck_filter`
  - it kept the accepted `short_digit_phrase_collect_pad0` winner and only set:
    - `stt_recheck_native_fast_audio_filter_enabled = False`

- evidence
  - artifact:
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260603_001655_249665_1512/benchmark_results.json`
  - result:
    - `33.065 / 44.698 / 47.053 / 1.4922`
  - compare accepted fast case2 band:
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_233944_942736_70106/benchmark_results.json`
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_234014_004291_70374/benchmark_results.json`
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_234028_513005_70356/benchmark_results.json`
    - accepted aggregate:
      - `14.079 / 85.199 / 85.537 / 0.4061`

- rejection reason
  - the filter toggle did not improve the collect path and instead collapsed straight back into the broad churn band:
    - `raw_segments 47`
    - `final_segments 60`
    - `word_precision_count 0`
    - `overlap_count 18`
  - `source_preservation:number_changed` rollback fired again
  - this is not a viable non-skip collect-path owner for current `case2`

- do not retry
  - do not reopen the `precise_recheck_filter` family on the current fast `case2` winner

# 2026-06-03 case2 low-vad phrase full speech filter rejected

- hypothesis
  - current fast `case2` planner narrowed the remaining owner to candidate truncation inside non-applied collect-path rows
  - maybe the low-VAD multi-token nondigit row `유지가 되고 있고요` was being truncated by the native fast recheck filter, so using the broader full speech filter only for that narrow row shape could improve precision output without disturbing the accepted fast band

- change
  - temporarily added a narrow helper that forced `stt_recheck_native_fast_audio_filter_enabled = False` only for low-VAD multi-token nondigit precision clips
  - temporarily added a benchmark-only variant:
    - `apple_case2_high_selective_timing_priority_short_digit_phrase_collect_pad0_low_vad_phrase_full_speech_filter`

- evidence
  - artifact:
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260603_003149_227060_67443/benchmark_results.json`
  - result:
    - `33.43 / 44.696 / 47.051 / 1.4925`
  - compare accepted fast case2 band:
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_233944_942736_70106/benchmark_results.json`
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_234014_004291_70374/benchmark_results.json`
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_234028_513005_70356/benchmark_results.json`
    - accepted aggregate:
      - `14.079 / 85.199 / 85.537 / 0.4061`

- rejection reason
  - this narrow speech-filter branch still collapsed into the same broad churn band:
    - `raw_segments 47`
    - `final_segments 60`
    - `word_precision_count 1`
    - `overlap_count 18`
  - `source_preservation:number_changed` rollback fired again
  - this is not a viable `collect_path_candidate_truncation_owner` branch for the current fast `case2`

- do not retry
  - do not reopen `low_vad_phrase_full_speech_filter`
  - keep the next bounded slice on other candidate-truncation owners, not full-speech filter overrides

# 2026-06-03 case2 long digit-leading left prepad rejected

- hypothesis
  - current fast `case2` planner still showed `17.8에서 연비가 안 바뀌는데` as a candidate-truncation collect-path owner
  - because the rejected candidate text was `.8에서 연비가`, maybe only the left edge of the collect clip was too tight
  - an asymmetric left prepad for long digit-leading phrase rows might restore the missing leading digits without disturbing the accepted short-digit winner

- change
  - temporarily added a narrow helper that increased only the left prepad for long digit-leading phrase precision clips
  - temporarily added a benchmark-only variant:
    - `apple_case2_high_selective_timing_priority_short_digit_phrase_collect_pad0_long_digit_leading_leftpad`

- evidence
  - artifact:
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260603_003842_426087_85978/benchmark_results.json`
  - result:
    - `34.72 / 44.696 / 47.051 / 1.4925`
  - compare accepted fast case2 band:
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_233944_942736_70106/benchmark_results.json`
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_234014_004291_70374/benchmark_results.json`
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_234028_513005_70356/benchmark_results.json`
    - accepted aggregate:
      - `14.079 / 85.199 / 85.537 / 0.4061`

- rejection reason
  - even the asymmetric left-prepad branch collapsed straight back into the same broad churn band:
    - `raw_segments 47`
    - `final_segments 60`
    - `word_precision_count 1`
    - `overlap_count 18`
  - `source_preservation:number_changed` rollback fired again
  - this is not a viable `collect_path_candidate_truncation_owner` branch for the `17.8에서 연비가 안 바뀌는데` row

- do not retry
  - do not reopen `long_digit_leading_leftpad`
  - keep the next bounded slice on other candidate-truncation owners, not asymmetric left-padding

# 2026-06-03 case2 low-vad nondigit right-tail padding restore rejected

- hypothesis
  - the remaining fast `case2` candidate-truncation owner for `유지가 되고 있고요` / `변화가 없네` looked like prefix-only truncation, so maybe the collect clip only needed a little more right-tail room to recover the suffix without reopening broad filters or thresholds

- change
  - temporarily added an asymmetric helper that increased only the right-tail collect padding for low-VAD multi-token nondigit precision clips
  - temporarily added a benchmark-only variant:
    - `apple_case2_high_selective_timing_priority_short_digit_phrase_collect_pad0_low_vad_nondigit_tail_pad035`

- evidence
  - artifact:
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260603_004811_561615_23331/benchmark_results.json`
  - result:
    - `34.124 / 44.696 / 47.051 / 1.4925`
  - compare accepted fast case2 band:
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_233944_942736_70106/benchmark_results.json`
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_234014_004291_70374/benchmark_results.json`
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_234028_513005_70356/benchmark_results.json`
    - accepted aggregate:
      - `14.079 / 85.199 / 85.537 / 0.4061`

- rejection reason
  - even this narrow low-vad suffix-rescue branch collapsed straight back into the same broad churn band:
    - `raw_segments 47`
    - `final_segments 60`
    - `word_precision_count 1`
    - `overlap_count 18`
  - `source_preservation:number_changed` rollback fired again
  - this is not a viable `collect_path_candidate_truncation_owner` branch for the current fast `case2`

- do not retry
  - do not reopen `low_vad_nondigit_collect_tail_padding_restore`
  - keep the next bounded slice on other candidate-truncation owners, not low-vad tail-padding restores

# 2026-06-03 case2 numeric spacing artifact edge-shift relaxation rejected

- hypothesis
  - the accepted fast `case2` planner narrowed the top remaining owner to `11.4 -> 11 .4`, which looked more like a pure numeric spacing artifact than a true truncation owner
  - if that row alone could tolerate a slightly larger word-precision edge-shift budget, maybe the candidate would apply without reopening broad threshold relaxation for other digit phrases

- change
  - temporarily added a narrow opt-in branch in `apply_word_precision_segments(...)` that only widened the effective edge-shift cap for pure-numeric spacing artifacts
  - temporarily added a benchmark-only variant:
    - `apple_case2_high_selective_timing_priority_short_digit_phrase_collect_pad0_numeric_spacing_artifact`

- evidence
  - artifact:
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260603_010458_767485_59690/benchmark_results.json`
  - result:
    - `39.202 / 44.501 / 46.894 / 1.489`
  - compare accepted fast case2 band:
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_233944_942736_70106/benchmark_results.json`
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_234014_004291_70374/benchmark_results.json`
    - `.codex_work/benchmarks/subtitle_pipeline_variants/20260602_234028_513005_70356/benchmark_results.json`
    - accepted aggregate:
      - `14.079 / 85.199 / 85.537 / 0.4061`

- rejection reason
  - even this ultra-narrow spacing-artifact branch collapsed into the same broad failure band:
    - `final_segments 60`
    - `word_precision_count 2`
    - `native_segments_summary.overlap_count 18`
  - `source_preservation:number_changed` rollback fired again and the final quality/timing band was far below the accepted fast `case2`
  - this is not a viable `candidate_text_artifact_owner` branch for the current `11.4` row

- do not retry
  - do not reopen `numeric_spacing_artifact_edge_shift_relaxation`
  - keep the next bounded slice on other non-threshold/non-edge-shift candidate-text owners, not pure-numeric edge-shift relaxation
