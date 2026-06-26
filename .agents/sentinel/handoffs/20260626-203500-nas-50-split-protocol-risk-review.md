DEX_REVIEW_READY
역할: 잼민이
범위: NAS 50 subtitle split protocol risk review
읽은 파일:
- docs/NAS_SUBTITLE_BENCHMARK_50_PLAN.md
- core/engine/subtitle_prompts.py
- core/personalization/runtime_lora_context.py
결론: NAS 50 정답 SRT 분석 기반 LoRA/LLM 프로토콜 반영과 관련하여, 반드시 다루어야 할 compatibility risk 3개, validation gap 3개 및 헤이딜러 벤치마크 score 상승 시의 false-positive 위험 요인을 정리했습니다.
findings:
1. **문서/프롬프트에 남겨야 할 Compatibility Risk 3개**:
   - **리스크 A (Legacy Save/Reopen 호환성)**: 새 프로토콜의 자막 분할 기준이 기존 `.aissproj` 파일에 저장된 세그먼트 배열 및 텍스트 구조와 충돌하여, 프로젝트 재개(reopen) 시 편집된 자막을 강제로 재분할하거나 유실시킬 위험이 있습니다.
   - **리스크 B (STT 후보잠금 절대규칙과의 충돌)**: `subtitle_prompts.py`에 정의된 `2-0-1. [후보 잠금 최우선]` 규칙에 따라, LoRA/LLM의 분할 지시어가 STT 원문 후보 범위를 변형하려 할 경우 강제 롤백(`2-10. [롤백 기준]`)이 발동되어 처리 루프 및 자원 낭비가 발생할 위험이 있습니다.
   - **리스크 C (기기별 Personalization 동기화 불일치)**: 다른 기기로 프로젝트를 이전할 때 기기마다 독립적으로 누적된 LoRA 학습 룰(`load_learned_rules`)의 차이로 인해, 동일 영상과 정답 SRT 하에서도 상이한 분할 결과가 초래될 수 있습니다.
2. **현 테스트 스위트 상의 Validation Gap 3개**:
   - **갭 A (VFR/드롭프레임 검증 부재)**: 현재 QA runner는 CFR(고정 프레임) 위주로 동작하므로, NAS 50의 29.97/59.94fps 드롭프레임 및 VFR 영상에서 발생할 수 있는 1프레임 미세 컷 정합도 정밀도 누수를 사전에 포착하기 어렵습니다.
   - **갭 B (LLM 컨텍스트 한계 및 Conservative 롤백 검증 미비)**: LoRA context가 프롬프트 길이를 대폭 증가시켜 LLM 컨텍스트 오버플로우가 나거나, conservative 모드가 오작동하여 분할/병합이 무시되는 런타임 현상을 탐지하는 전용 가드레일이 없습니다.
   - **갭 C (SRT-only 오프라인 벤치마크 테스트 미비)**: 미디어(영상)나 VAD 없이 직접 SRT 파일만 올려 벤치마크를 돌릴 때, 컷 경계 정보 부재로 인해 싱크가 밀리거나 계산 오류가 발생하는 경로에 대한 자동화 테스트가 누락되어 있습니다.
3. **헤이딜러 기존 Benchmark Score 상승 시 False-Positive 위험**:
   - 헤이딜러의 기존 감점은 실제 정보 유실이 아니라 정답지(615개) 대비 generated(417개)의 자막 병합에 기인한 개수 스코어 하락(`count_score = 67.805`)이 핵심 원인이었습니다.
   - 새 프로토콜 적용으로 점수가 올랐다면, 실제 한국어 품질이나 정합도가 향상된 것이 아니라 단지 **정답 자막의 쪼개기 단위에 LLM 프롬프트를 오버피팅(Overfitting)시킨 결과**일 수 있습니다. 이 경우 가독성이 오히려 훼손되거나 다른 50개 영상으로 확산 적용 시 전체 품질 스코어가 동반 붕괴되는 부작용이 발생할 수 있습니다.
defer: 없음
덱스 확인 포인트: 본 분석 자료는 덱스(Codex) 측에서 NAS 50개 영상을 활용한 신규 자막 분할 프로토콜을 반영할 때, 저장 호환성 훼손 방지 및 스코어 왜곡에 속지 않는 E2E 게이트 수립에 활용됩니다.
