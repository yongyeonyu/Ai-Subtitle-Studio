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
  결론: native policy helper는 parity mismatch가 해소될 때까지 default 승격하지 않는다. adoption report는 `blocked_quality_mismatch`로 표시한다.
  artifact: `tools/benchmark_native_policy_engine.py --docs 500 --rounds 12 --lora-rounds 2`

- `mode_fast_as_quality_equivalent_x5_default`: X5 품질 동일 조건에서 `mode_fast`를 최종 기본 알고리즘으로 승격하는 방향
  결과: X5 60초 10회 반복에서 평균 `10.373s`로 빠르지만 quality gate `0/10`.
  품질: quality `71.514`, final segment `17`로 기준 `mode_high_piecewise_drift` quality `72.989`, final segment `24`보다 낮았다.
  결론: `mode_fast`는 Fast 모드 속도 후보로는 유지하되, 품질 동일 조건의 최종 기본 알고리즘으로 승격하지 않는다.
  artifact: `output/manual_verification/latest/idea_full_execute_20260521-0821/x5_modes_repeat10_quality_gate/repeat_summary.md`
