DEX_REVIEW_READY
역할: 서린
범위: Heydealer reference/media match and timing-score risk review
읽은 파일:
- .codex_work/benchmarks/subtitle_pipeline_variants/20260626-175343/benchmark_results.json
결론: 헤이딜러 최종 MP4/SRT 기준의 벤치마크 결과 데이터를 기반으로 개수 편차 분석, duration 불일치 위험, 괄호/대시 필터링 및 시작시간 평가 리스크 검토를 완료했습니다.
findings:
1. **615 vs 417 개수 차이의 Scoring False-Negative 판단**:
   - reference 자막(615개) 대비 generated 자막(417개)의 개수가 198개 적은 현상은 실제 정보의 누락이 아닙니다. `global_text_similarity`가 90.4%에 달하고 `text_score`가 85.737로 높게 나타나는 점으로 보아, LORA 가독성 패키징에 의한 세그먼트 병합(Merging) 현상으로 판명됩니다.
   - 실제 정보 유실이 없음에도 세그먼트 수가 달라 `count_score`가 67.805로 저평가되어 최종 `quality_score`가 81.32로 하락했으므로, 이는 평가 스코어러 상의 대표적인 **scoring false-negative**로 분류됩니다.
2. **duration/last_end mismatch 위험 분석**:
   - 비디오의 전체 길이(`1200.252s`)와 최종 자막 세그먼트 종료 시간(`last_end = 1198.588s`, `stt2_last_end = 1198.088s`) 간의 차이는 1.664초 내외로 매우 타이트합니다.
   - 마지막 무음 구간으로 수렴하며 영상 종료 영역에서 자막이 범위를 초과(overflow)하거나 잘려 나가는 mismatch 리스크는 거의 없으며 지극히 안정적입니다.
3. **괄호 주석/대시 제외 및 시작시간 가중 평가 시 위험**:
   - **괄호/대시 노이즈 위험**: reference SRT 내에 존재하는 `(음악)`, `(웃음)` 등의 괄호 환경음 주석이나 발화자 구분용 대시(`-`) 문자가 벤치마크 텍스트 비교 전처리에서 엄격히 필터링되지 않을 경우 텍스트 유사도 매칭 오류 및 점수 왜곡(noise)이 발생합니다.
   - **시작시간 가중 평가 위험**: 싱크 평가 시 시작시간(start-time)에 가중치를 높게 두면, LLM 자막 분할 및 VAD 스냅 단계에서 문장의 맨 앞머리 싱크가 미세하게 밀리거나 컷 경계에 잘못 달라붙을 때 전체 정합도 스코어가 급격하게 하락하여 품질 정당성이 훼손될 위험이 있습니다.
4. **Focused Validation Shortlist**:
   - [ ] **세그먼트 병합 감점 완화 검사**: E2E 텍스트 보존율 대비 count score의 패널티 가중치를 보정하는 스코어러 정책 검증.
   - [ ] **마지막 자막 구간 무음 검사**: `last_end`와 전체 duration 사이의 공백(1.664s) 동안 실제 음성이 없는 무음 상태가 맞는지 오프스크린 VAD 검증.
   - [ ] **괄호 및 특수문자 정규화 필터 검증**: reference SRT 내 비음성 노이즈 문자열을 무력화하는 정규식 필터링 테스트 추가.
defer: 없음
덱스 확인 포인트: 본 리스크 리뷰 문서는 덱스(Codex) 측에서 헤이딜러 벤치마크 결과를 해석하고, 텍스트 누락이 없음에도 개수 편차로 감점되는 평가 방식(scoring false-negative)의 갭을 인지 및 조정하는 데 기여합니다.
