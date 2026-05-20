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
