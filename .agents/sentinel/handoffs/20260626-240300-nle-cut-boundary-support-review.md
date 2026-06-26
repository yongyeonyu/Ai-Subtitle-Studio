DEX_REVIEW_READY
역할: 잼민이
범위: NLE/cut-boundary read-only support
읽은 파일:
- docs/ARCHITECTURE.md
- docs/HANDOFF.md
- docs/FEATURE_REGISTRY.md
- core/cut_boundary.py
결론: AI Subtitle Studio의 cut-boundary 및 NLE 변환 상태를 조사하여, read-only baseline의 상태, 잔여 갭, 성긴 보폭 및 롤백에 따른 컷 경계 누락 위험과 검증을 위한 pytest 대상을 정리했습니다.
findings:
1. **내부 NLE 변환의 Read-only Baseline 상태 확인**:
   - 현재 `v04.00.17` 기준 NLE 변환은 **"read-only baseline"** 상태입니다.
   - 기존 `.aissproj` 저장 스키마나 메모리 내 mutable 상태는 레거시대로 유지하고, 렌더링 및 러프컷 내보내기 시점에 `NLESnapshot` 객체로 일방향 투영(read-only adapter)하여 render plan을 수립하는 비파괴 설계로 제약되어 있습니다. 쓰기 레이어까지 통합하는 full runtime migration 단계는 아닙니다.
2. **잔여 갭(Remaining Gaps)**:
   - **NLE 어댑터 역직렬화(reverse-write) 부재**: NLE snapshot 상에서 가공된 타이밍 편집 데이터를 레거시 `.aissproj` 저장 포맷으로 역동기화하는 쓰기 기능이 누락되어 있습니다.
   - **Cross-device Relink/Cache UX 비동화**: 캐시 누락이나 미디어 경로 유실 시, NLE 레이어와 기존 `project_assets.py` 간의 relocation 및 캐시 데이터 동기화 상태 전파 갭이 있습니다.
   - **Timeline UI와 NLE 시퀀스의 물리 분리**: NLE 시퀀스/트랙 데이터가 메모리 도메인에는 존재하나, 실제 timeline canvas 렌더러는 기존 flat 구조를 유지하여 UI 단의 완벽한 멀티트랙화가 구현되지 않았습니다.
3. **성긴 보폭(Coarse Stride) 및 롤백에 따른 Cut-boundary 누락 위험**:
   - **성긴 보폭(Coarse Stride) 위험**: 연산 최소화를 위해 visual cut 스캔 보폭(stride)을 너무 넓게 가져갈 경우, 수 프레임 이내의 숏 컷(flash cut)을 완전히 놓치는 누락(miss)이 발생하여 마그넷 스냅이 불가능해집니다.
   - **롤백에 의한 컷 정보 소실**: STT/LLM 재시도 실패로 롤백이 돌 때, 롤백 이전 프레임에서 확정되었던 유효 컷 마커들이 휘발되거나 타임스탬프 괴리로 유령 마커(ghost marker)화될 위험이 존재합니다.
4. **실행해야 할 추천 테스트(Tests to run)**:
   - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_nle_snapshot.py` (NLE 스냅샷 투영 검증)
   - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_v2_output_compat.py` (EDL 및 roughcut snapshot 호환성 검증)
   - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_boundary_alignment.py` (hard-cut 유지 및 provisional snap 검증)
   - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_pipeline_cut_boundary_cache.py` (컷 경계 롤백/쉬프트 검증)
   - `./venv/bin/python tools/qa_suite_runner.py quick` (전체 smoke 검증)
defer: 없음
덱스 확인 포인트: 본 조사 문서는 덱스(Codex) 측에서 NLE write path 마이그레이션 방향을 모색하고, 컷 검출 보폭 조정 및 롤백 시 마커 안정성 보장을 위한 아키텍처 제약 사항으로 회수 및 참조될 수 있습니다.
