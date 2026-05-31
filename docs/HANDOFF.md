# Handoff

이 문서는 다음 세션이 빠르게 이어받을 수 있도록 현재 작업 상태와 종료 기준을 남기는 곳입니다. 긴 작업 일지 전체를 붙이는 용도가 아니라, 다음 작업자가 바로 움직일 수 있는 최소 사실을 남기는 용도입니다.

## When to update

아래 중 하나에 해당하면 세션 종료 전에 이 파일을 갱신합니다.

- 코드 또는 문서를 의미 있게 수정했을 때
- 검증 명령이나 기준을 바꿨을 때
- owner 파일이나 책임 경계를 바꿨을 때
- 다음 세션이 알아야 할 열린 리스크가 남았을 때

## What to include

- 이번 세션의 작업 범위
- 실제 수정한 파일
- 실행한 검증과 결과
- 남은 리스크 또는 미확인 사항
- 다음 세션의 첫 권장 행동

## What not to include

- 개인 메모
- 비공개 경로
- 장문의 사고 과정
- 재현 불가능한 임시 판단

## Update rules

- 상대 경로를 사용합니다.
- 사실만 적고 과장하지 않습니다.
- 다음 세션이 그대로 따라 할 수 있는 명령과 파일명을 남깁니다.
- `ACTION_ITEMS.md`와 충돌하는 임시 우선순위를 만들지 않습니다.

## Current handoff snapshot

- Date: `2026-05-31`
- Scope: 수동 저장 버튼 경로를 빠른 체크포인트 저장 구조로 조정하고, `.aissproj` 프로젝트 파일을 pretty JSON에서 binary envelope 포맷으로 전환한 상태가 현재 기술 기준선입니다. 기본 수동 저장은 SRT를 atomic replace로 가볍게 쓰고 반복 백업/동일 내용 재쓰기를 피하며, 프로젝트 payload는 MessagePack binary로 저장하고 매우 큰 payload에서만 zlib 압축을 적용합니다. 프로젝트 접근은 `read_project_file` / `write_project_file` / `read_project_storage_payload` 경로로 통일했습니다. 추가로 지연 프로젝트 저장은 Qt 위젯/에디터 상태를 UI 스레드에서 스냅샷으로만 캡처하고, 순수 `save_project()` / project file write는 worker thread에서 수행하도록 분리했습니다.
- Scope: owner 방향은 `native migration` 중단, 기존 Python/PyQt6 source app 지속 사용으로 정리되었습니다. 이번 세션에서는 코드 변경 없이 `AGENTS.md`, `ACTION_ITEMS.md`, `README.md`, `docs/PROJECT_STATE.md`를 source-app 기준으로 다시 맞췄고, 다음 세션이 native 전환을 기본 전제로 잡지 않도록 문서 방향을 통일했습니다.
- Updated files:
  - `docs/ARCHITECTURE.md`
  - `docs/FEATURE_REGISTRY.md`
  - `core/engine/srt_writer.py`
  - `core/project/project_io.py`
  - `core/pipeline/pipeline_helpers.py`
  - `requirements-mac.txt`
  - `tests/test_editor_autosave_cleanup.py`
  - `tests/test_cp03_cp04_status_ui.py`
  - `tests/test_project_context.py`
  - `tests/test_project_cut_boundary_resume.py`
  - `tests/test_recovery_state.py`
  - `tests/test_stt_mode_project_state.py`
  - `ui/editor/editor_actions.py`
  - `ui/editor/editor_save_manager.py`
  - `ui/editor/editor_segments_runtime_cache.py`
  - `ui/home_sidebar.py`
  - `ui/main/main_file_ops.py`
  - `ui/main/main_window.py`
  - `ui/menu_bar.py`
  - `AGENTS.md`
  - `ACTION_ITEMS.md`
  - `README.md`
  - `docs/HANDOFF.md`
  - `docs/PROJECT_STATE.md`
- Validation:
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py` -> `85 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_recovery_state.py tests/test_stt_mode_project_state.py tests/test_project_cut_boundary_resume.py` -> `13 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cp03_cp04_status_ui.py -k "trim_cut_boundary_state_for_partial_rerun or restart_prescan_uses_current_cut_boundary_settings or clears_roughcut"` -> `2 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_autosave_cleanup.py tests/test_project_segment_reload.py -k "save or project or reload"` -> `132 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_stt_lattice.py tests/test_subtitle_accuracy_graph.py` -> `12 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_autosave_cleanup.py` -> `47 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_engine_settings.py -k "save_srt"` -> `5 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_autosave_cleanup.py tests/test_subtitle_engine_settings.py -k "manual_save or deferred_project_save or pending_deferred_project_save or persist_editor_srts_prefers_opened_source_srt_path or save_srt"` -> `17 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_autosave_cleanup.py -k "export_dialog_does_not_prompt_when_only_stale_dirty_flags_remain or pending_internal_project_refresh_does_not_mark_clean_editor_dirty"` -> `2 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_global_menu_bar.py` -> `3 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_cp03_cp04_status_ui.py -k "save_clears_dirty_until_real_subtitle_edit or project_file_change_marks_editor_dirty" tests/test_sidebar_terminal_layout.py -k "quick_exit or exit_confirm"` -> `6 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_autosave_cleanup.py -k "deferred_project_save or manual_save_defers_project_save or close_flushes_deferred_project_save or qobject_deferred_project_save"` -> `5 passed`
  - `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_context.py -k "save_project or project_io or stt_mode or recovery_state"` -> `32 passed`
  - `./venv/bin/python -m py_compile ui/editor/editor_save_manager.py ui/editor/editor_segments_runtime_cache.py ui/editor/editor_actions.py ui/main/main_file_ops.py ui/menu_bar.py ui/home_sidebar.py ui/main/main_window.py core/pipeline/pipeline_helpers.py tests/test_editor_autosave_cleanup.py`
  - `./venv/bin/python -m py_compile ui/editor/editor_save_manager.py tests/test_editor_autosave_cleanup.py`
  - `./venv/bin/python -m py_compile core/project/project_io.py core/engine/srt_writer.py ui/editor/editor_save_manager.py tests/test_project_context.py tests/test_project_cut_boundary_resume.py tests/test_recovery_state.py tests/test_stt_mode_project_state.py tests/test_cp03_cp04_status_ui.py`
  - SRT 저장 임시 벤치: 2500 segments에서 반복 저장 시 동일 내용 백업 파일을 추가 생성하지 않음(`backup_files=1`).
  - 프로젝트 파일 임시 벤치: 2500 segments payload에서 legacy pretty JSON `1743886 bytes` 대비 binary project `923065 bytes`(`size_ratio=0.529`), legacy pretty JSON write 평균 `0.02434s` 대비 binary write 평균 `0.00191s`, legacy stdlib read 평균 `0.00491s` 대비 binary read 평균 `0.00222s`.
  - `rg -n "mac-native|native migration|NATIVE_LIB_PLAN|SOURCE_APP_CONTINUATION_V4_0_15|04.00.15-source-app" AGENTS.md ACTION_ITEMS.md README.md docs/HANDOFF.md docs/PROJECT_STATE.md`로 문서 방향과 메타데이터 일치 여부를 확인했습니다.
  - `git diff --check -- core/project/project_io.py requirements-mac.txt tests/test_project_context.py tests/test_project_cut_boundary_resume.py tests/test_recovery_state.py tests/test_stt_mode_project_state.py tests/test_cp03_cp04_status_ui.py docs/ARCHITECTURE.md docs/FEATURE_REGISTRY.md docs/HANDOFF.md core/engine/srt_writer.py ui/editor/editor_save_manager.py tests/test_editor_autosave_cleanup.py tests/test_subtitle_engine_settings.py` 통과
  - `git diff --check -- AGENTS.md ACTION_ITEMS.md README.md docs/HANDOFF.md docs/PROJECT_STATE.md` 통과
- Open risks:
  - 이전 세션의 저장 경로 변경은 아직 source app 실사용으로 재검증이 덜 됐습니다. 대형 프로젝트에서 저장 직후 `자막 출력` prompt, `빠른 저장 체크포인트 완료`, `프로젝트 지연 저장 완료` 로그를 다시 봐야 합니다.
  - 새 프로젝트 파일은 사람이 직접 `json.load`로 열 수 없습니다. 테스트/도구가 raw project payload를 봐야 하면 `core.project.project_io.read_project_storage_payload()`를 사용해야 합니다.
  - `.aissproj` binary envelope 전환 이후 실제 reopen 흐름에서 세그먼트, STT preview, voice activity, roughcut/project state 유지가 source app에서 다시 확인돼야 합니다.
  - 지연 프로젝트 저장은 worker thread로 분리됐지만, UI 스레드 스냅샷 단계에서 `collect_editor_project_aux_state()`가 voice activity refresh와 각종 runtime row 복사를 수행합니다. 초대형 프로젝트에서는 이 스냅샷 구간이 다음 병목인지 source app에서 다시 봐야 합니다.
  - `EditorActionsMixin`에는 legacy dirty helper 복제본이 남아 있습니다. 현재 `EditorWidget` MRO에서는 `EditorSaveManagerMixin`이 우선이라 실동작은 새 helper를 타지만, 추후 mixin 정리 시 중복 제거 여부를 판단해야 합니다.
- Recommended next step:
  - source app에서 Macau/X5 프로젝트를 열고 저장 버튼 경로를 다시 확인합니다. 터미널의 `빠른 저장 체크포인트 완료`와 `프로젝트 지연 저장 완료` 로그 시점을 기록하고, 앱 종료 후 같은 `.aissproj` 재열기까지 확인해 저장/복원 회귀가 없는지 먼저 증빙합니다.
