DEX_REVIEW_READY
역할: 서린
범위: Cayenne High E2E validation checklist review
읽은 파일:
- test_result.md
- docs/HANDOFF.md
결론: 카이엔(Cayenne) High E2E 재실행 결과를 독립적이고 엄격하게 검증하기 위한 4개 영역의 물리 체크리스트를 정의하였습니다.
findings:
1. **정답지(Reference SRT) 전처리 검사항목**:
   - [ ] 정답 SRT 내 `(음악)`, `(웃음)` 등의 괄호 주석문(parenthetical comments)이 정확히 제거 및 정규화되었는가?
   - [ ] 발화 기호 등으로 사용되는 `- ` (dash) text-only 라인이 텍스트 매칭 검증 대상에서 완벽히 제외되었는가?
2. **싱크 평가 공식(Scoring Policy) 검사항목**:
   - [ ] 싱크 정합도 점수 산출 시 시작시간(start-time)의 정합성에 종료시간(end-time)보다 더 높은 가중치가 정상 부여되는가?
3. **시각적 컷-시작 정합 검사항목 (7건의 프레임 기준)**:
   - [ ] 7건의 컷-시작 정합 지점이 단순 시간(sec) 소수점 비교 대신, `frame_time_map`에서 매핑된 정밀 프레임(frame_index) 단위 기준으로 검증되는가?
   - [ ] visual cut(78.900s)과 reference 자막 시작(78.280s)이 불일치하는 예외적인 충돌 구간이 뭉개지지 않고 검증 리포트에 "충돌 구간(Conflict)"으로 명확히 구분 및 별도 표기되는가?
4. **자막 퇴화 방지(Drift Guards) 검사항목**:
   - [ ] 최종 자막 수(Subtitle Count)가 정답 자막(285~291 rows 내외) 대비 유실 또는 왜곡 병합되지 않았는가?
   - [ ] 첫 자막 시작(first) 및 끝 자막 종료(last) 경계의 전체 타임라인 왜곡(overall time drift)이 0.05초 이내로 제어되는가?
   - [ ] 컷 경계 스냅 처리 중 자막의 종료 시간단(end) 오차가 점진적으로 누적(cumulative drift)되지 않고 방어되는가?
defer: 없음
덱스 확인 포인트: 본 E2E 검증 체크리스트는 덱스(Codex) 측에서 Cayenne 자막 싱크 및 컷-스냅 알고리즘 재실행 결과를 최종 QA 승인하기 위한 엄격한 게이트라인으로 회수 및 활용됩니다.
