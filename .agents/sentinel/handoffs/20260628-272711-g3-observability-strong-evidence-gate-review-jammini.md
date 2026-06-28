DEX_REVIEW_READY
역할: 잼민이
범위: AI Subtitle Studio v04.01.07 G3 live runtime observability strong-evidence gate review
읽은 파일:
- tools/remote_verify.py
- tests/test_remote_verify_actions.py
결론: v04.01.07 버전에 적용된 G3 실시간 런타임 관측성 강한 증거 게이트(strong-evidence gate)의 사양과 검증 커버리지 리뷰를 완료했습니다.

*   **프로젝트명**: AI Subtitle Studio
*   **저장소 루트**: `/Users/u_mo_c/Downloads/ai_subtitle_studio`

---

### 🔍 1. 다중 pre-final 관측 제약 검증 (Two Distinct Pre-final Polls)

*   **최소 2회 이상 관측 제약**:
    - `_pre_final_observation_summary` 에서 각 `VAD`, `STT1`, `STT2` 트랙이 서로 다른 `poll_index`를 가진 active pre-final 상태(`pre_final_active=True`)의 status 응답 샘플 중 **최소 2회 이상 관측**되어야만 합격으로 간주합니다.
    - 활성 상태 중 관측 횟수가 부족한 트랙이 있을 경우 `insufficient_pre_final_observations` 에러를 방출하여 검증을 `blocked` 처리합니다.
    - 완료 이후의 샘플(`generation_completed=True`)은 pre-final 카운팅에서 완벽히 배제됩니다.

---

### 🛡️ 2. 완료 조건 및 압축 페이로드 차단 (Generation & Compact Payloads)

*   **미완료 시 차단**:
    - 자막 생성의 최종 완료 플래그(`generation_completed`)가 관측 주기 내에 단 한 번도 수집되지 않으면 `generation_not_completed` 에러를 터트려 전체 하네스를 블락합니다.
*   **컴팩트 전송 강제화**:
    - `nle_runtime_tracks` 의 `compact_payload` 필드가 False인 샘플이 하나라도 감지될 경우 `compact_runtime_payload_contract_failed` 에러를 즉각 수록합니다.

---

### 🔒 3. 민감 데이터 파일 저장 누출 차단 (Redaction & Sample Export)

*   **데이터 검사 및 격리**:
    - `status_samples.json` (또는 `observability_samples.jsonl`) 파일에 status 샘플들을 저장하기 전, 모든 샘플에 대해 `_contains_raw_runtime_payload` 검사기를 통과시켜 자막 원본 텍스트가 유출되지 않도록 전수 보장합니다.
    - 요약 보고서(`live_nle_runtime_proof.json` 및 `live_nle_runtime_proof.md`)를 작성할 때도, 대용량의 상세 `samples` 배열을 일절 포함하지 않고 메타데이터와 요약 카운트만 수록하는 Summary Redaction 계약이 정상 준수되고 있음을 확인했습니다.

---

### ⚖️ 4. 증거 한계 및 주의 명시 (No Overstatement)

*   **관측 범위 구분**:
    - 검증 하네스 보고서 내 주의 노트를 통해 본 하네스가 Mocked/현장 런타임 텔레메트리 관측 정보 수집용임을 공고히 하여, 실제 실미디어 visual 렌더링 품질, 속도 개선, App Store 샌드박스 readiness 등 타 물리적 영역의 검증으로 확대 해석되거나 과장되지 않도록 제한하고 있습니다.
*   **테스트 케이스Parity**:
    - `test_remote_verify_actions.py` 에 새로 추가된 `test_live_nle_proof_blocks_single_pre_final_observation_per_track` 등의 테스트 케이스를 통해, 단 1회 관측 시 `insufficient_pre_final_observations` 이슈 발생 및 블락 판정이 의도대로 검증되고 있음을 완벽히 증명했습니다.
