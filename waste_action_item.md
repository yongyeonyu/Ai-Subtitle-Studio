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
