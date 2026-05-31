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
- Snapshot type: carry forward the last save/checkpoint technical baseline plus the later source-app-direction document cleanup.

### Current direction

- `native migration`은 현재 active roadmap이 아닙니다.
- 기본 제품 라인은 기존 Python/PyQt6 source app입니다.
- 다음 세션은 native 전환을 전제로 시작하지 말고, source-app 실증과 회귀 방지부터 이어가야 합니다.

### Technical baseline carried forward

- 수동 저장 버튼 경로는 빠른 체크포인트 저장 구조를 기준선으로 유지합니다.
- `.aissproj` 프로젝트 파일은 pretty JSON 대신 binary envelope 포맷을 사용합니다.
- 기본 수동 저장은 SRT를 atomic replace로 가볍게 쓰고, 반복 백업과 동일 내용 재쓰기를 피합니다.
- 프로젝트 payload는 MessagePack binary로 저장하고, 매우 큰 payload에서만 zlib 압축을 적용합니다.
- 프로젝트 접근 경로는 `read_project_file`, `write_project_file`, `read_project_storage_payload`로 통일되어 있습니다.
- 지연 프로젝트 저장은 Qt 위젯/에디터 상태를 UI 스레드에서 스냅샷으로만 캡처하고, 순수 `save_project()` / project file write는 worker thread에서 수행하도록 분리되어 있습니다.

### Updated files in the carried-forward checkpoint

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

### Validation summary

#### Targeted pytest passes

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

#### Static checks and document consistency

- `./venv/bin/python -m py_compile ui/editor/editor_save_manager.py ui/editor/editor_segments_runtime_cache.py ui/editor/editor_actions.py ui/main/main_file_ops.py ui/menu_bar.py ui/home_sidebar.py ui/main/main_window.py core/pipeline/pipeline_helpers.py tests/test_editor_autosave_cleanup.py`
- `./venv/bin/python -m py_compile ui/editor/editor_save_manager.py tests/test_editor_autosave_cleanup.py`
- `./venv/bin/python -m py_compile core/project/project_io.py core/engine/srt_writer.py ui/editor/editor_save_manager.py tests/test_project_context.py tests/test_project_cut_boundary_resume.py tests/test_recovery_state.py tests/test_stt_mode_project_state.py tests/test_cp03_cp04_status_ui.py`
- `rg -n "mac-native|native migration|NATIVE_LIB_PLAN|SOURCE_APP_CONTINUATION_V4_0_15|04.00.15-source-app" AGENTS.md ACTION_ITEMS.md README.md docs/HANDOFF.md docs/PROJECT_STATE.md`로 문서 방향과 메타데이터 일치 여부를 확인했습니다.
- `git diff --check -- core/project/project_io.py requirements-mac.txt tests/test_project_context.py tests/test_project_cut_boundary_resume.py tests/test_recovery_state.py tests/test_stt_mode_project_state.py tests/test_cp03_cp04_status_ui.py docs/ARCHITECTURE.md docs/FEATURE_REGISTRY.md docs/HANDOFF.md core/engine/srt_writer.py ui/editor/editor_save_manager.py tests/test_editor_autosave_cleanup.py tests/test_subtitle_engine_settings.py` 통과
- `git diff --check -- AGENTS.md ACTION_ITEMS.md README.md docs/HANDOFF.md docs/PROJECT_STATE.md` 통과

#### Observed benchmark and behavior notes

- SRT 저장 임시 벤치: 2500 segments에서 반복 저장 시 동일 내용 백업 파일을 추가 생성하지 않음(`backup_files=1`).
- 프로젝트 파일 임시 벤치: 2500 segments payload에서 legacy pretty JSON `1743886 bytes` 대비 binary project `923065 bytes`(`size_ratio=0.529`), legacy pretty JSON write 평균 `0.02434s` 대비 binary write 평균 `0.00191s`, legacy stdlib read 평균 `0.00491s` 대비 binary read 평균 `0.00222s`.

### Open risks

- 이전 세션의 저장 경로 변경은 아직 source app 실사용으로 재검증이 덜 됐습니다. 대형 프로젝트에서 저장 직후 `자막 출력` prompt, `빠른 저장 체크포인트 완료`, `프로젝트 지연 저장 완료` 로그를 다시 봐야 합니다.
- 새 프로젝트 파일은 사람이 직접 `json.load`로 열 수 없습니다. 테스트/도구가 raw project payload를 봐야 하면 `core.project.project_io.read_project_storage_payload()`를 사용해야 합니다.
- `.aissproj` binary envelope 전환 이후 실제 reopen 흐름에서 세그먼트, STT preview, voice activity, roughcut/project state 유지가 source app에서 다시 확인돼야 합니다.
- 지연 프로젝트 저장은 worker thread로 분리됐지만, UI 스레드 스냅샷 단계에서 `collect_editor_project_aux_state()`가 voice activity refresh와 각종 runtime row 복사를 수행합니다. 초대형 프로젝트에서는 이 스냅샷 구간이 다음 병목인지 source app에서 다시 봐야 합니다.
- `EditorActionsMixin`에는 legacy dirty helper 복제본이 남아 있습니다. 현재 `EditorWidget` MRO에서는 `EditorSaveManagerMixin`이 우선이라 실동작은 새 helper를 타지만, 추후 mixin 정리 시 중복 제거 여부를 판단해야 합니다.

### Recommended next step

- source app에서 Macau/X5 프로젝트를 열고 저장 버튼 경로를 다시 확인합니다. 터미널의 `빠른 저장 체크포인트 완료`와 `프로젝트 지연 저장 완료` 로그 시점을 기록하고, 앱 종료 후 같은 `.aissproj` 재열기까지 확인해 저장/복원 회귀가 없는지 먼저 증빙합니다.

## 2026-05-31 Addendum - Manual Interaction Priority

### Scope

- 생성 완료 직후 editor readiness 경로에서 무거운 cleanup/waveform 번들을 다음 이벤트 턴으로 미루는 패치를 유지한 상태에서,
- 사용자가 직접 `스크럽`하거나 `subtitle text focus`에 들어가면 post-generation follow-up이 편집 체감을 가로막지 않도록 foreground priority 훅을 추가했습니다.
- Antigravity `잼민이`에게 같은 owner 파일 범위 리뷰를 보내고, 구현 전/후 합동 판단을 받아 `Accept` 결론까지 확인했습니다.

### Files touched in this slice

- `ui/editor/editor_pipeline_completion.py`
- `ui/main/main_runtime_cleanup.py`
- `ui/editor/ux/editor_timeline_video.py`
- `ui/editor/ux/subtitle_text_edit.py`
- `tests/test_editor_autosave_cleanup.py`
- `tests/test_timeline_playhead_fit.py`
- `tests/test_subtitle_text_edit_keys.py`
- `tests/test_sidebar_terminal_layout.py`
- `idea.md`

### Validation run

- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_timeline_playhead_fit.py -k "scrub_updates_playhead_immediately_and_uses_lightweight_preview_seek or scrub_throttles_video_seek_during_fast_mouse_moves or scrub_start_prioritizes_manual_editor_runtime_once_per_active_scrub"` -> `3 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_subtitle_text_edit_keys.py -k "focus_in_disables_window_space_shortcut_while_editing or focus_in_prioritizes_manual_editor_runtime_after_generation"` -> `2 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_sidebar_terminal_layout.py -k "prioritize_video_playback_runtime_defers_heavy_release_while_starting_playback or prioritize_manual_editor_interaction_runtime_defers_heavy_release_while_editing or prioritize_video_playback_runtime_skips_while_generation_is_still_running or prioritize_manual_editor_interaction_runtime_skips_while_generation_is_still_running"` -> `4 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_autosave_cleanup.py` -> `48 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py` -> `86 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_editor_roughcut_draft.py -k 'foreground_activity or cancel_post_generation_roughcut'` -> `4 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_video_player_widget.py -k 'prioritiz'` -> `2 passed`
- `./venv/bin/python -m py_compile ui/main/main_runtime_cleanup.py ui/editor/ux/editor_timeline_video.py ui/editor/ux/subtitle_text_edit.py tests/test_timeline_playhead_fit.py tests/test_subtitle_text_edit_keys.py tests/test_sidebar_terminal_layout.py`
- `git diff --check -- ui/main/main_runtime_cleanup.py ui/editor/ux/editor_timeline_video.py ui/editor/ux/subtitle_text_edit.py tests/test_timeline_playhead_fit.py tests/test_subtitle_text_edit_keys.py tests/test_sidebar_terminal_layout.py`
- `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick` -> `failed_count=0`, artifact `output/manual_verification/latest/qa_suite_quick_20260531_203839`
- `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py major` -> `failed_count=0`, artifact `output/manual_verification/latest/qa_suite_major_20260531_204209`

### Jammini review outcome

- 판정: `Accept`
- `roughcut_reason`은 스크럽과 텍스트 포커스를 별도 문자열로 나누지 말고 `"편집 시작"`으로 통합 유지 권장
- save/load 및 playback runtime semantics에는 현재 패치 범위에서 회귀가 없다고 봄
- 잼민이 집중 테스트 추가 실행 결과:
  - `tests/test_editor_roughcut_draft.py -k 'foreground_activity or cancel_post_generation_roughcut'` -> `4 passed`
  - `tests/test_video_player_widget.py -k 'prioritiz'` -> `2 passed`
  - `tests/test_sidebar_terminal_layout.py -k 'prioritize_video_playback_runtime'` 계열로 runtime defer 시맨틱을 추가 확인
- 다음 보강 후보는 `scrub <-> play` 비동기 스트레스 시나리오

### Remaining risk

- 오프스크린/단위 테스트 기준 회귀는 없지만, Macau/X5 실앱에서 generation 직후 즉시 scrub/play/text focus를 섞을 때 frame shake나 GC 지연 누적이 체감되지 않는지 아직 안 봤습니다.

### Recommended next step

- source app에서 Macau/X5 fixture를 열고 generation 완료 직후 바로 `scrub -> play -> subtitle text focus -> save/reopen` 순서의 실앱 스모크를 한 번 더 남깁니다. 이때 전체 프레임 shake, `00:00 / 00:00` 잔상, playhead ghost, 저장 후 재열기 회귀가 없는지 같이 확인합니다.
