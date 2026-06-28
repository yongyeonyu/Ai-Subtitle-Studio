DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio NLE next safe slice scout

findings:
1. **NLE 차기 안전 슬라이스 1개 추천**:
   - **추천 항목**: **"NLE Project Save-Reload Memory & Adapter Cache Consistency Audit Tooling" (저장/불러오기 캐시 일관성 진단 보강)**
2. **선정 사유 및 안전성**:
   - **안전성**: UI/UX 변경, per-pixel drag write, NLE 디스크 스키마(.aissproj) 변경이 일체 없는 비파괴 진단(read-only audit & tests) 조각이므로 오너 승인 없이 안전하게 수행 가능.
3. **이전 완료 항목과의 차별점 (중복 방지)**:
   - 이전 작업들은 dual-write 11개 operation 및 timeline canvas projection 등의 기능적 정합성에 치중함.
   - 본 추천 조각은 "프로젝트 저장/불러오기 반복 시, NLEState 및 memory adapter 캐시 인스턴스가 중복 생성되어 메모리 누수(leak)를 유발하거나 stale 캐시를 타는 구조적 한계"를 비파괴적으로 체크하는 최초의 일관성 전용 감사 도구임.
4. **관련 파일 경로**:
   - `tools/audit_nle_adapter_consistency.py` [NEW]
   - `tests/test_nle_adapter_consistency.py` [NEW]
5. **예상 Acceptance Gate**:
   - 5회 이상 save/reopen 반복 유닛 테스트 시 NLE adapter 인스턴스 활성 카운트가 `1` 이하로 강제 유지되는지 검사.
   - 기존 `invalid_duration_count=0`, `non_monotonic_count=0`, `overlap_count=0` 통과 유지.
6. **추천 테스트**:
   - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_adapter_consistency.py`
