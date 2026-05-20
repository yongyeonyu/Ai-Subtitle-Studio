# Performance Ideas

## 2026-05-20 Scope
- 대상 미디어: 마카오 `/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217225132_0079_D.MP4`, X5 `test video/X5_시승기_후반.MP4`
- 실행 방식: `./venv/bin/python tools/verify_full_media_pipeline.py --mode fast --repeat 10`
- 품질 기준: `final_segment_count`, `raw_segment_count`, `variant_score.score`, `llm_rollback_count`
- 반복 최적화 사이클: 3회

## 현재 채택 후보
- 채택 후보: `candidate1`
- 유지 코드: [core/pipeline/single_pipeline.py](/Users/u_mo_c/Downloads/ai_subtitle_studio/core/pipeline/single_pipeline.py:537)
- 유지 이유: 자막 품질은 유지하면서 X5 평균 시간이 가장 좋았고, 폐기 후보 2개보다 전체 균형이 안정적이었다.

## 기준값

### 이전 기준 참고값
- 마카오 baseline: avg `6.680` / min `6.583` / max `6.845`
  artifact: `output/manual_verification/latest/20260520_perf_cycle2_baseline/baseline_current_macao`
- X5 baseline(canonical): avg `61.750` / min `61.193` / max `62.571`
  artifact: `output/manual_verification/latest/20260520_perf_cycle2_baseline/baseline_current_x5_canon`

### 이번 작업의 현재 기준값
- 현재 HEAD baseline은 `candidate1` 결과를 사용한다.
- 마카오 current: avg `6.770` / min `6.604` / max `7.240`
- X5 current: avg `61.252` / min `60.705` / max `62.201`
  artifact: `output/manual_verification/latest/20260520_perf_cycle2_candidate1`

## 3회 반복 결과

### 1차 채택: checkpoint cleanup 완화
- 변경 포인트:
  [core/pipeline/single_pipeline.py](/Users/u_mo_c/Downloads/ai_subtitle_studio/core/pipeline/single_pipeline.py:537),
  [core/pipeline/single_pipeline.py](/Users/u_mo_c/Downloads/ai_subtitle_studio/core/pipeline/single_pipeline.py:728),
  [core/pipeline/single_pipeline.py](/Users/u_mo_c/Downloads/ai_subtitle_studio/core/pipeline/single_pipeline.py:991),
  [core/pipeline/single_pipeline.py](/Users/u_mo_c/Downloads/ai_subtitle_studio/core/pipeline/single_pipeline.py:1080)
- 요약: `audio_extract_done`, `stt_transcribe_done`, `stt_optimizer_threads_done`, `save_export_done`에서 평시 강제 cleanup/trim 호출을 줄이고, `critical`일 때만 MemoryGuard 자동 정리에 더 의존하도록 조정.
- 결과:
  마카오 avg `6.770` (`+1.35%` vs 이전 baseline)
  X5 avg `61.252` (`-0.81%` vs 이전 baseline)
- 품질:
  마카오 `final=5`, `raw=3`, `variant=62.0`, `rollback=0`
  X5 `final=111`, `raw=96`, `variant=61.2829`, `rollback=0`
- 판정: 현재 채택

### 2차 폐기: `cut_prescan_done` cleanup 제거
- 변경 시도: `cut_prescan_done`의 `cleanup=True` 제거
- 가설: prescan 직후 trim이 불필요한 no-op 비용일 수 있다.
- 결과:
  마카오 avg `7.474` (`+10.40%` vs current)
  X5 avg `64.709` (`+5.64%` vs current)
- 품질:
  마카오 `final=5`, `raw=3`, `variant=62.0`, `rollback=0`
  X5 `final=111`, `raw=96`, `variant=61.2829`, `rollback=0`
- 판정: 폐기
  artifact: `output/manual_verification/latest/20260520_perf_cycle3_candidate2`

### 3차 폐기: `subtitle_optimize_done` warning-stage GPU trim 축소
- 변경 시도: `subtitle_optimize_done`의 `include_gpu=True` 제거
- 가설: 청크 후처리마다 warning-stage GPU trim이 반복되며 X5 누적 비용을 키울 수 있다.
- 결과:
  마카오 avg `6.682` (`-1.30%` vs current)
  X5 avg `63.007` (`+2.87%` vs current)
- 품질:
  마카오 `final=5`, `raw=3`, `variant=62.0`, `rollback=0`
  X5 `final=111`, `raw=96`, `variant=61.2829`, `rollback=0`
- 판정: 폐기
  artifact: `output/manual_verification/latest/20260520_perf_cycle3_candidate3`

## 관찰 정리
- `cut_prescan_done` cleanup 제거는 메모리를 남겨서 빨라지기보다, 오히려 X5에서 이후 STT/후처리 구간 비용을 키웠다.
- `subtitle_optimize_done` warning-stage GPU trim 제거도 마카오 단건은 약간 좋아졌지만, X5 반복 평균과 분산을 개선하지 못했다.
- 채택 후보와 폐기 후보 모두 마카오/X5의 `final_segment_count`, `raw_segment_count`, `variant_score`, `rollback`은 동일했다.
- X5 run_10 기준 `process_snapshot_after.total_matched=2`로 남는 프로세스는 `ollama serve`와 `ollama runner`뿐이었다.

## 다음 아이디어
1. `SubtitleGenerationMemoryGuard`에 stage별 trim 실행 횟수와 wall time을 기록해서, 느려지는 구간을 로그로 바로 상관관계 분석한다.
2. `core/runtime/memory_manager.py`의 디스크 캐시 사용량 스캔 TTL/루트 인덱스 TTL을 벤치 대상으로 올린다.
3. `core/native_swift_runtime_cache.py` 호출 수와 native bridge elapsed를 함께 기록해서, 정리 호출 빈도보다 bridge 비용이 더 큰지 확인한다.
4. `core/audio/media_processor_transcribe.py`의 STT release 경로에서 warning 단계 `clear_audio_model_memory_caches(include_gpu=False)` 호출량을 계수화한다.
5. Ollama `serve/runner` 상주 시간이 반복 생성 평균에 미치는 영향을 분리 측정한다.
6. 품질 불변 hot path가 확인되면 `stt_lattice`, `subtitle_timing`, `word_resegmenter` 같은 결정적 루프를 native 후보로 올린다.

## 결론
- 이번 3회 반복에서 가장 좋은 후보는 `candidate1`이다.
- 현재 기준으로는 "cleanup을 더 넓게 줄이는 것"보다 "어느 trim이 실제로 느리게 만드는지 stage별 비용을 먼저 계측하는 것"이 다음 최적화의 우선순위다.
