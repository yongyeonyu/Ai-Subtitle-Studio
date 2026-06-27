DEX_REVIEW_READY
역할: 잼민이 (lightweight chores / prep work)
프로젝트: AI Subtitle Studio
레포지토리 경로: /Users/u_mo_c/Downloads/ai_subtitle_studio
범위: AI Subtitle Studio next uncovered NLE release source risk scout

findings (12줄 이내 요약):
1. **선택된 후보**: **수동 임시 편집점 추가 및 삭제 (Provisional Cut Boundary Edit)**
2. **Owner function**: `ui/editor/editor_scan_cut_core.py` 의 `_on_provisional_cut_boundary_requested` / `_on_provisional_cut_boundary_delete_requested`
3. **Release boundary 근거**: 타임라인에 임시 편집선(`provisional`)을 우클릭 등으로 생성/제거 완료하여 메모리 `_auto_cut_boundary_scan_lines` 에 커밋하는 시점.
4. **UI-shape/metadata 위험**: NLE `cut_boundaries` 구조와 GUI 데이터 간 동기화 불일치 시, save/reopen 후 수동 편집선이 타임라인 상에서 유실되거나 틀어지는 리스크.
5. **필수 guard**: 편집점의 `time` 값은 반드시 `_snap_to_frame`을 통과한 FPS-aligned frame 정수 시간이어야 하며, 동일 좌표 중복 추가 가드 적용 필수.
6. **추천 pytest 명령**: `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py -k "cut_boundary or cut_boundaries"`
