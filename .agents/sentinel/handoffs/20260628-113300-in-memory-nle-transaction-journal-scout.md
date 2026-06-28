DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio in-memory NLE transaction journal scout

결론: accept (in-memory-only 진단 조각으로 즉각 수용 권장)

findings:
1. **`NLEProjectState` 내의 runtime history 수신 검토**:
   - `NLEProjectState` dataclass에 `operations_history: list[NLEEditorOperation] = field(default_factory=list)` 멤버를 추가하여 메모리상에서만 최대 50개의 ring-buffer 또는 단순 append list 형태로 연산 이력을 적체 가능함.
2. **Dual-write metadata 보존성**:
   - `nle_dual_write.py` 연산 완료 시 `NLEEditorOperation` 반환 레코드 구조가 operation 고유 메타데이터(kind, target_ids 등)를 100% 캡처하여 history에 축적할 수 있음을 검증함.
3. **디스크 저장 시 schema strip guard 작동성**:
   - `nle_persistence_guard.py` 내의 `strip_unapproved_nle_persistence_fields`가 project_io.write 단에서 작동하여, 임시 런타임 이력(`operations_history` 등)이 `.aissproj` 디스크 파일에 영구 기록되는 것을 완전히 소거(strip)해 줌을 확인.
4. **Focused Test 후보**:
   - `tests/test_nle_operation_journal_audit.py` [NEW]를 신설하여 11개 dual-write 연산 유발 시 in-memory history 누적 여부 및 디스크 저장 시 strip 무결성을 검증.
5. **안전성 판정**: 실제 undo/redo UI 트리거 변경 및 persisted disk file 쓰기가 없으므로 Parity 유지 측면에서 무결한 비파괴적 개선임.

defer:
- **실제 undo/redo UI 단축키 및 이벤트 루프 연동**: UI interaction 변경 리스크를 피하기 위해 UI 및 state machine 전환은 Defer 함.
- **디스크 직렬화 저장**: operation journal을 디스크 파일 포맷에 명시 저장하는 행위는 디스크 스키마 변경 요건이므로 Defer 함.
- **per-pixel drag write**: 드래그 실시간 쓰기 금지.
