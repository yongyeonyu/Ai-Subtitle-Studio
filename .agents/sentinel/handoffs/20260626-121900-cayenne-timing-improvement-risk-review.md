DEX_REVIEW_READY
역할: 서린
범위: Cayenne start-time/cut-start timing improvement risk review
읽은 파일:
- core/engine/subtitle_timing.py
- core/cut_boundary.py
- tests/test_subtitle_boundary_alignment.py
- docs/HANDOFF.md
결론: Cayenne 정답 SRT 기준의 싱크 및 컷 정합도 개선과 관련하여, 프로덕션 런타임의 reference 의존성 위험, 시각적 컷 누락으로 인한 false confidence, 기존 timing/STT/LLM/VAD 정책 drift 리스크 및 검증 숏리스트를 정리했습니다.
findings:
1. **Production 보정의 Reference SRT 의존 위험**: 런타임 보정 알고리즘(`subtitle_timing.py`)이 평가용 reference SRT의 타임스탬프 정보를 소스로 참조하게 설계된다면, 정답 자막이 존재하지 않는 실제 운영 환경에서는 작동할 수 없으며 시스템 크래시를 유발합니다. 따라서 프로덕션 보정은 오직 VAD, STT 후보군 및 시각적 컷 경계 정보(Visual Cut)만을 단독 원천으로 사용해야 합니다.
2. **Visual Cut Metadata 누락 시 False Confidence**: 컷 경계 싱크 rescore 평가 시, 최종 자막 세그먼트(final segments)에 실제 컷 경계 정렬 결과(`_cut_boundary_guard_policy` 등)가 메타데이터로 명시 기입되어 보존되지 않는 한, 오프셋 계산 수치만 우연히 들어맞는 경우에 "개선됨"으로 잘못 평가하는 QE 통계적 오류(false confidence)가 발생합니다.
3. **기존 Subtitle Timing/STT/LLM/VAD 정책 Drift 위험**: 컷 경계 스냅(magnetization) 가중치를 강하게 조절할 경우, VAD 음성 경계 감지나 STT 단어 정렬 결과, 혹은 LLM의 자막 문맥 분할 정책과 충돌하여 자막이 부자연스럽게 잘려 나가거나 품질 점수가 저하되는 drift 위험이 있습니다.
4. **Focused Validation Shortlist**:
   - **Reference 격리 검사**: reference SRT 인풋이 누락된 환경에서 timing 파이프라인의 정상 구동 및 예외 처리를 검증하는 회귀 테스트 수립.
   - **Visual Cut 메타데이터 단언**: 컷 정렬 완료 세그먼트에 타임스탬프 가드 메타데이터가 존재함을 단언하는 유닛 테스트 추가.
   - **종단간 품질 스코어 비교**: 보정 정책 변경 전후로 `tools/qa_suite_runner.py` major 스위트를 돌려 overall quality score와 세그먼트 수의 왜곡(drift) 여부를 측정하는 QA 게이트 수립.
defer: 없음
덱스 확인 포인트: 본 리스크 리뷰 문서는 덱스(Codex) 측에서 Cayenne 자막 싱크 정확도 및 컷 정합도 개선 로직 설계 시, 오버피팅 배제 및 기존 timing/STT/LLM/VAD 정책과의 안전한 격리를 보장하기 위한 아키텍처 제약사항으로 회수 및 활용될 수 있습니다.
