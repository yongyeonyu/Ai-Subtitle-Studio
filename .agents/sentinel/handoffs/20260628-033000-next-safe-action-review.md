DEX_REVIEW_READY
역할: 한결 (architecture & rollback safety)
범위: Next safe action after STT/AppStore hold
읽은 파일:
- `ACTION_ITEMS.md` ([ACTION_ITEMS.md](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/ACTION_ITEMS.md))
- `docs/HANDOFF.md` ([docs/HANDOFF.md](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/docs/HANDOFF.md))
- `core/project/nle_persistence_guard.py` ([core/project/nle_persistence_guard.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/core/project/nle_persistence_guard.py))
- `core/project/project_io.py` ([core/project/project_io.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/core/project/project_io.py))
- `tests/test_project_nle_persistence_guard.py` ([tests/test_project_nle_persistence_guard.py](file:///Users/u_mo_c/Downloads/ai_subtitle_studio/tests/test_project_nle_persistence_guard.py))

결론: 현재 STT latency 최적화(NAS-off) 및 App Store 패키징(owner approval 전)이 모두 hold 상태인 상황에서, 덱스가 즉시 착수해도 되는 안전하고 영향도가 좁은 NLE 영속성(Persistence) 연동 설계 조각을 발굴하였습니다.

findings:
1) **추천 조각**:
   - **NLE persistence cutover support review & prep**: 런타임 write 에 적용된 NLE dual-write 오퍼레이션들을 디스크 저장/복구(sqlite/json 세이브 파일 포맷) 단계까지 안전하게 이중화하여 저장 시의 데이터 정합성을 검증하고, legacy save/reload 하위 호환성을 완벽하게 격리 보장하기 위한 nle_persistence_guard의 차기 결합 구조 분석 및 설계.
2) **근거 파일/테스트**:
   - `core/project/nle_persistence_guard.py`
   - `core/project/project_io.py`
   - `core/project/project_manager.py`
   - `tests/test_project_nle_persistence_guard.py`
   - `tests/test_project_nle_snapshot.py`
3) **금지할 범위**:
   - 대표님 명시 승인 없이 `core/project/project_io.py` 내부의 실질 디스크 쓰기 방식을 legacy 방식에서 NLE 단독 구조로 전환하는 작업 (하위 호환 붕괴 리스크 방지).
   - UI/UX 변경 및 STT latency trim 알고리즘 터치.
   - packaging/signing 스크립트 실행.
4) **verdict**:
   - **VERDICT: ACCEPT (Review/Prep Only)**

defer: (none)
덱스 확인 포인트:
- NLE 영속성 마이그레이션(Persistence Cutover) 역시 하위 호환성 및 세이브 유실 방지를 위한 strict QE 검증이 필수적이므로, 실제 코드 변경을 배제한 사전 영향도 review/prep 조각으로 진입하는 것에 대한 타당성 동의 여부.
