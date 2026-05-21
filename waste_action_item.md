# Waste Action Items

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
