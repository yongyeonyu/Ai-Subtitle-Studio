DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio NLE persistence/save-render-export next gap scout

findings:
1. **두 후보 비교 분석**:
   - **후보 (1) persisted NLE project fields**: 디스크 저장 schema (JSON)에 직접 NLE 필드를 직렬화하여 쓰는 변경. 이는 하위 호환성 및 오너의 명시적 디스크 포맷 승인 가드가 있어 현재로서는 **대단히 High-Risk (보류 권장)**.
   - **후보 (2) save-render-export ownership cleanup**: 디스크 JSON 포맷은 레거시 `subtitle_vector` 스키마를 100% 보존하되, 메모리/어댑터 단의 불필요한 이중 데이터 맵핑 및 project IO 검증 흐름을 atomically clean-up하는 변경. **Low-Risk (가장 추천)**.
2. **추천 다음 슬라이스**: **후보 (2) save-render-export ownership cleanup**
   - **선정 사유**: 디스크 호환성을 전혀 위협하지 않으며, 메모리 hydration 단계에서 redundant한 legacy data check를 걷어내어 코드 청결성을 향상시킬 수 있음.
3. **관련 파일**: `core/project/project_io.py`, `core/project/nle_render_export_parity.py`, `core/project/nle_persistence_guard.py`
4. **focused tests**:
   - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_persistence_guard.py`
   - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_render_export_parity.py`
5. **Acceptance Gates**:
   - 디스크 JSON 내 `nle`, `nle_snapshot`, `_nle_project_state` 필드가 unapproved 상태로 디스크에 써지지 않고 `nle_persistence_guard` 가 차단하는 성질 보존.
   - 기존 quick QA 및 major QA 에서 save/reopen roundtrip이 100% 통과(failed_count=0).
6. **Rollback plan**:
   - project_io.py 변경사항을 revert하고, 기존의 2중 serialization flow 복구.
