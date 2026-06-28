DEX_REVIEW_READY
역할: 잼민이
범위: AI Subtitle Studio G3 live runtime observability proof harness review
읽은 파일:
- tools/remote_verify.py
- tests/test_remote_verify_actions.py
결론: 덱스가 신규 추가한 G3 실시간 런타임 관측성 검증 하네스(observability proof harness)의 구조 분석 및 타겟 검증성 파일 스코프 리뷰를 완료했습니다.

*   **프로젝트명**: AI Subtitle Studio
*   **저장소 루트**: `/Users/u_mo_c/Downloads/ai_subtitle_studio`

---

### 🛡️ 1. 실시간 트랙 텔레메트리 검증 (Pre-final Track Evidence)

*   **참조 트랙 counts 증거화**:
    - `_LIVE_NLE_REQUIRED_RUNTIME_TRACKS = ("VAD", "STT1", "STT2")` 명세를 통해, 자막 생성이 완료되기 전(`pre_final_active`) 수집된 `status` 샘플에서 VAD, STT1, STT2 카운트가 실제로 관측(observed)되는지 파악하고 표 형태(`live_nle_runtime_proof.md`)로 증거화합니다.
    - 활성 상태 중 단 1회라도 해당 트랙 카운트가 감지되지 않으면 `missing_pre_final_tracks` 이슈로 처리되어 검증을 차단합니다.

---

### 🔒 2. 상태 통신 데이터 정화 검증 (Raw Payload Leak Protection)

*   **자막 데이터 누출 필터링**:
    - `_contains_raw_runtime_payload` 함수를 통해 `segments`, `stt_preview_segments`, `vad_segments`, `voice_activity_segments` 등의 대용량 텍스트/세그먼트 원본이 통신 응답에 직접 섞여 나가지 않았는지 전수 스캔합니다.
    - 데이터 유출 감지 시 `raw_runtime_payload_leak` 이슈가 트리거되어, UDP 대역폭 방어 및 보안 경계선 훼손을 자동 탐지합니다.

---

### ⚖️ 3. 저장 권한 및 예산 준수 검증 (Final Authority & Budget Contract)

*   **Final Authority 계약**:
    - `"final"` 레인만 `authoritative_for_save_export=True` 권한을 갖는지 확인하고, 다른 임시/참조 레인(VAD, STT)이 저장 권한을 탈취하면 `final_authority_contract_failed` 블로커를 유도합니다.
*   **Projection Budget 계약**:
    - `shares_subtitle_worker_pool=False`, `dedicated_worker_count=0` 등 워커 스레드 점유 금지 계약을 상시 모니터링하여 위반 시 `live_projection_budget_contract_failed`로 마킹합니다.

---

### ✍️ 4. 한계 명시 및 과장 배제 (Observed Bounds)

*   **관측 범위 가이드라인 명시**:
    - 레포트 최하단 노트를 통해 본 하네스가 **순수 런타임 상태 관측성만을 증거화**하며, 이것이 자 자막 품질 승인, 성능 속도 최적화, 스토리지 컷오버 승인을 갈음할 수 없다는 한계점(`Notes`)을 명확히 명시하고 있습니다.
*   **테스트 커버리지**:
    - `test_remote_verify_actions.py` 상에서 `test_live_nle_proof_accepts_pre_final_compact_runtime_tracks` 및 `test_live_nle_proof_blocks_raw_payload_and_final_authority_drift` 등 성공/실패 시나리오를 충실히 단위 검증하고 있음을 확인했습니다.
