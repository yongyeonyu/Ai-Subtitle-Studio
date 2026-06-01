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

## 2026-06-01 Addendum - Apple Speech Hidden Challenger Slice

### Scope

- Apple 제공 `SpeechTranscriber` / `SpeechDetector`를 새 `STT3` UI 옵션으로 노출하지 않고, 기존 High 경로 안의 hidden challenger backend로 넣기 위한 첫 슬라이스를 추가했습니다.
- 이번 슬라이스는 실제 batch transcription 전면 교체가 아니라 `support probe + hidden routing plan + High preset gate`까지를 닫는 범위입니다.
- 의도는 WhisperKit/MLX 기본 경로를 유지한 채, fixture score가 더 좋을 때만 Apple route를 승격할 수 있게 owner 경계를 먼저 만드는 것입니다.

### Files touched in this slice

- `core/audio/apple_speech_native.py`
- `core/audio/stt_backend_router.py`
- `core/audio/vad_backend_router.py`
- `core/audio/stt_quality_presets.py`
- `core/audio/audio_preset_data.py`
- `core/mode_manager.py`
- `core/runtime/config.py`
- `core/settings_profiles.py`
- `native/macos/AIStudioNative/Sources/AIStudioCore/AppleSpeechSupport.swift`
- `native/macos/AIStudioNative/Sources/AIStudioNativeCLI/main.swift`
- `tests/test_apple_speech_native.py`
- `tests/test_runtime_optimization_profile.py`
- `tests/test_stt_quality_presets.py`

### Validation run

- `./venv/bin/python -m py_compile core/audio/apple_speech_native.py core/audio/stt_backend_router.py core/audio/vad_backend_router.py core/audio/stt_quality_presets.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_apple_speech_native.py tests/test_runtime_optimization_profile.py tests/test_stt_quality_presets.py`
- `git diff --check`

### Remaining risk

- 아직 실제 `SpeechTranscriber` batch transcription execution path는 media processor에 연결하지 않았습니다. 현재는 support probe와 challenger plan만 들어간 상태입니다.
- `SpeechDetector`도 독립 글로벌 VAD replacement가 아니라 Apple STT challenger에 결합된 보조 detector로만 계획되어 있습니다.
- 다음 단계에서 실제 fixture benchmark를 붙일 때는 current WhisperKit/MLX 결과와 같은 scoring schema로 비교해야 하며, 점수 승리 전에는 High 기본 route를 바꾸면 안 됩니다.

### Recommended next step

- `core/audio/media_processor_transcribe_run.py` 쪽에 Apple challenger benchmark hook을 추가하고, Macau/X5 fixture에서 WhisperKit/MLX vs Apple 결과를 같은 `candidate_ranker`/quality gate 기준으로 비교합니다.

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

## 2026-05-31 Addendum - Cross-Project Cooperation Kit

### Scope

- `덱스`와 `잼민이` 협업 방식을 다른 저장소에도 바로 옮길 수 있도록 root `cooperation.md`를 추가했습니다.
- 새 프로젝트에 초깃값을 빠르게 떨구기 위한 `tools/cooperation_bootstrap.sh`도 같이 추가했습니다.
- 문서 지도에 `cooperation.md`를 등록해 다음 세션이 협업 규칙을 바로 찾을 수 있게 했습니다.

### Files touched in this slice

- `cooperation.md`
- `tools/cooperation_bootstrap.sh`
- `README.md`
- `docs/README.md`
- `docs/HANDOFF.md`

### Validation run

- `bash -n tools/cooperation_bootstrap.sh`
- `git diff --check`

### Remaining risk

- 다른 저장소에 이식할 때는 해당 저장소의 실제 read-order 문서와 owner 파일 이름에 맞게 bootstrap prompt를 한 번은 조정해야 합니다.
- Antigravity helper 명령(`ag-send-last`, `ag-review-file` 등)이 없는 환경에서는 shell example을 그 환경에 맞는 wrapper로 바꿔야 합니다.

### Recommended next step

- 새 프로젝트 루트에서 `tools/cooperation_bootstrap.sh /absolute/project/path` 형태로 초기 문서를 생성한 뒤, 그 저장소의 `AGENTS.md` / `ACTION_ITEMS.md` / `docs/HANDOFF.md` 체계에 맞게 read order만 조정합니다.

## 2026-05-31 Addendum - Roughcut Save/Reopen Roundtrip

### Scope

- 러프컷 UI 가시화 이후 남아 있던 실제 reopen 경계 보강에 집중했습니다.
- 목표는 `.aissproj` 저장본에서 `selected candidate / safety filter / selected chapter`가 살아남고, roughcut work mode 프로젝트를 열면 roughcut 화면까지 자동으로 다시 진입하는지 증빙하는 것이었습니다.
- 이 과정에서 `core/roughcut/models.py::roughcut_result_from_dict()`가 frame-only compact candidate payload를 그대로 dataclass로 복원하려다 reopen 경계에서 깨질 수 있는 구멍을 닫았습니다.

### Files touched in this slice

- `core/roughcut/models.py`

## 2026-06-01 Addendum - Roughcut LLM Candidate Vertical Columns

### Scope

- roughcut 좌측 상단 `LLM 후보` 영역을 `가로로 긴 바` 대신 `세로로 긴 후보 기둥 3개`로 고정했습니다.
- 각 후보 기둥은 좌우로 나란히 배치되고, 기둥 내부에는 roughcut 세그먼트가 위에서 아래로 수직 적재됩니다.
- 기존 후보 저장/복원, 후보 선택, 우측 플레이어/메뉴, 하단 roughcut 상세 기능은 그대로 유지합니다.

### Files touched in this slice

- `ui/roughcut/roughcut_widget.py`
- `ui/roughcut/roughcut_state.py`
- `ui/roughcut/roughcut_table.py`
- `tests/test_roughcut_ui_v2.py`
- `docs/HANDOFF.md`

### Validation run

- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py tests/test_roughcut_candidates.py tests/test_app_command_bridge.py` -> `94 passed`
- `./venv/bin/python -m py_compile ui/roughcut/roughcut_widget.py ui/roughcut/roughcut_state.py ui/roughcut/roughcut_table.py tests/test_roughcut_ui_v2.py`
- `git diff --check -- ui/roughcut/roughcut_widget.py ui/roughcut/roughcut_state.py ui/roughcut/roughcut_table.py tests/test_roughcut_ui_v2.py docs/HANDOFF.md`

### Visual proof

- latest mockup: `output/manual_verification/latest/roughcut_vertical_columns_mockup.png`
- proof intent:
  - 후보 프레임 3개는 `좁고 긴 세로 기둥`
  - 그 3개를 `좌우 병렬`로 배치
  - 각 기둥 안 roughcut 세그먼트는 `위에서 아래로 수직 적재`

### Remaining risk

- 현재 증빙은 오프스크린 mockup 기준입니다. source app 실앱에서 후보가 실제 3개 이상 저장된 프로젝트를 열어도 같은 밀도와 클릭 흐름이 유지되는지 한 번 더 봐야 합니다.
- 후보 기둥 안 세그먼트가 많아질 때 스크롤 또는 정보 생략 규칙이 더 필요한지 실사용에서 확인이 필요합니다.

### Recommended next step

- source app에서 roughcut 후보가 여러 개인 fixture를 열고 `후보 기둥 클릭 -> 세그먼트 확인 -> reorder/preview`를 실앱으로 한 번 더 남깁니다. 필요하면 그 다음 조각에서 후보 기둥 내부 `썸네일/칩/요약` 밀도만 좁게 조정합니다.

## 2026-06-01 Addendum - Roughcut Multi-Row Density And Candidate Restore Fix

### Scope

- 선택된 major card가 실제로 chapter row 여러 개를 보여주도록 density 제한을 풀었습니다.
- 동시에 frame-only candidate payload에서 `minor_groups` 복원 시 `start/end`가 빠져 `editor_post_generation_roughcut_draft` 후보 전환이 깨지던 복원 경계를 수정했습니다.
- source app 재기동 뒤 실앱 확인까지 이어갔고, 여기서 `roughcut-select-candidate`의 즉시 응답과 실제 visible UI/status 사이에 새 불일치가 남는 것도 확인했습니다.

### Files touched in this slice

- `ui/roughcut/roughcut_major_panel.py`
- `core/roughcut/models.py`
- `tests/test_roughcut_ui_v2.py`
- `tests/test_roughcut_candidates.py`
- `docs/HANDOFF.md`

### Validation run

- `./venv/bin/python -m py_compile ui/roughcut/roughcut_major_panel.py tests/test_roughcut_ui_v2.py core/roughcut/models.py tests/test_roughcut_candidates.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py -k 'unselected_major_cards_stay_compact_while_selected_card_expands or five_major_cards_keep_compact_height_budget or selected_major_card_expands_to_show_multiple_minor_rows or drag_surfaces_emit_major_and_minor_reorder_requests'` -> `4 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_candidates.py -k 'frame_only or apply_candidate_payload_restores_selected_chapter_and_filter or payload_keeps_multiple_candidates_and_selected_candidate'` -> `3 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py -k 'thumbnail_button_emits_preview_request_for_minor_row'` -> `1 passed`
- `git diff --check -- ui/roughcut/roughcut_major_panel.py tests/test_roughcut_ui_v2.py core/roughcut/models.py tests/test_roughcut_candidates.py`

### Real-app observations

- clean restart sequence that restored automation reachability:
  - `kill -9 25594`
  - `nohup ./venv/bin/python main.py >/tmp/ai_subtitle_studio_codex.log 2>&1 &`
  - after restart, `./venv/bin/python tools/appctl.py ping` returned `ok=true`
- latest source-app snapshot with the current restart line:
  - `output/manual_verification/latest/roughcut_draft_candidate_fixed_20260601.png`
- automation proof after the candidate restore fix:
  - `./venv/bin/python tools/appctl.py roughcut-select-candidate --candidate-id editor_post_generation_roughcut_draft`
  - immediate command result returned `ok=true`
  - returned runtime payload claimed:
    - `selected_candidate_id == editor_post_generation_roughcut_draft`
    - `selected_chapter_id == B_0014`
    - `visible_row_count == 45`
    - `visible_segment_ids == [A, C, B, D]`
- however, the subsequent global `status` payload and captured UI still showed:
  - `selected_candidate_id == suite_multicandidate_previous`
  - `visible_row_count == 1`
  - visible UI remained on the previous-candidate single-card view

### Remaining risk

- `roughcut-select-candidate` is no longer crashing on frame-only `minor_groups`, but the app-command immediate return can now disagree with the visible source-app UI and the later global `status` snapshot.
- because of that mismatch, the latest source-app run does **not** yet prove that the new expanded selected-card multi-row density is visible on the real `editor_post_generation_roughcut_draft` candidate.

### Recommended next step

- inspect the `roughcut-select-candidate` owner path for split-brain state:
  - `ui/main/app_command_bridge_handlers.py`
  - `ui/roughcut/roughcut_widget.py::automation_select_candidate`
  - `ui/roughcut/roughcut_state.py::_apply_candidate_payload`
  - any alternate roughcut page ownership used by `open-roughcut`
- once the command result, global `status`, and actual UI agree again, re-run:
  - `open-project ...DJI_20260217224203_0075_D_multicandidate.aissproj`
  - `open-roughcut`
  - `roughcut-select-candidate --candidate-id editor_post_generation_roughcut_draft`
  - snapshot the expanded selected-card view and then continue to minor-row drag proof.

## 2026-06-01 Addendum - Roughcut Candidate Convergence And Minor Reorder Proof

### Scope

- the earlier `roughcut-select-candidate` mismatch turned out not to be a permanent split state. With a short settle window, global `status` and the visible UI converge to the selected draft candidate.
- after that convergence check, source app proof was extended to:
  - draft candidate visible multi-row layout
  - chapter-level reorder inside a major card
  - ordered preview activation following the reordered chapter order
  - roughcut SRT export after the reorder

### Commands and evidence

- restart + reopen sequence:
  - `kill -9 25594`
  - `nohup ./venv/bin/python main.py >/tmp/ai_subtitle_studio_codex.log 2>&1 &`
  - `./venv/bin/python tools/appctl.py ping`
  - `./venv/bin/python tools/appctl.py open-project /Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/qa_suite_major_20260601_021538/_suite_fixtures/DJI_20260217224203_0075_D_multicandidate.aissproj`
  - `./venv/bin/python tools/appctl.py open-roughcut`
- draft candidate convergence:
  - `./venv/bin/python tools/appctl.py roughcut-select-candidate --candidate-id editor_post_generation_roughcut_draft`
  - immediate command result returned the new candidate state
  - after `sleep 1.5`, `./venv/bin/python tools/appctl.py status` matched the same candidate and visible rows
- artifacts:
  - `output/manual_verification/latest/roughcut_draft_candidate_fixed_after_wait_20260601.png`
  - `output/manual_verification/latest/roughcut_minor_reorder_after_move_20260601.png`
  - `output/manual_verification/latest/roughcut_minor_reorder_after_move_20260601_status.json`
  - `output/manual_verification/latest/roughcut_sequence_preview_active_20260601.png`
  - `output/manual_verification/latest/roughcut_sequence_preview_active_20260601_status.json`
  - `output/manual_verification/latest/roughcut_minor_reorder_export_20260601.srt`

### Proven current behavior

- candidate convergence:
  - after the short settle window, `roughcut_runtime.selected_candidate_id == editor_post_generation_roughcut_draft`
  - `visible_row_count == 45`
  - `visible_segment_ids == [A, C, B, D]`
- selected-card multi-row live view:
  - `roughcut_draft_candidate_fixed_after_wait_20260601.png` shows the expanded B card with multiple visible card-segment rows instead of the former single-row cap
- chapter-level reorder:
  - before move, selected chapter was `B_0015`
  - `./venv/bin/python tools/appctl.py roughcut-move-chapter --direction up`
  - resulting `chapter_order` and `visible_chapter_ids` changed from `... B_0014, B_0015, B_0016 ...` to `... B_0015, B_0014, B_0016 ...`
  - snapshot `roughcut_minor_reorder_after_move_20260601.png` and status json capture this state
- ordered preview:
  - `./venv/bin/python tools/appctl.py roughcut-play-sequence`
  - runtime then reported `sequence_preview_active == true`
  - later status also showed playback active (`video_playback_state == playing`) and advanced selection (`selected_chapter_id == B_0017`)
- export:
  - `./venv/bin/python tools/appctl.py roughcut-export-srt /Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/roughcut_minor_reorder_export_20260601.srt`
  - exported file exists and `subtitle_count == 28`

### Remaining risk

- the current automation evidence proves reorder state, sequence activation, and export after reorder, but it does not yet prove a direct mouse drag gesture for the minor row in the live source app. The feature path is present and protected, but the latest proof uses automation selection/move commands plus live snapshots.
- `candidate_state` still reads `이전 자막 기준` even on the draft candidate path, so the label semantics should be rechecked separately before calling the roughcut flow fully polished.

### Recommended next step

- keep the current live fixture open and try a direct minor-row drag gesture proof on the expanded B card surface.
- after that, audit `candidate_state` semantics so the label shown beside the active draft candidate matches the real source-signature meaning.

## 2026-06-01 Addendum - Roughcut Card Segment Subtitle Visibility

### Scope

- `ui/roughcut/roughcut_major_panel.py`의 카드 세그먼트 row에서 `자막 세그먼트`가 너무 얇게 지나가던 부분을 보강했습니다.
- 이제 각 카드 세그먼트 안에서 `자막 개수`와 `실제 자막 스니펫`이 같이 보이게 했고, 제목/시간/상태 아래에서 바로 읽히도록 좁게 정리했습니다.
- roughcut 후보 세로 기둥 3개, 카드 reorder, 우측 플레이어/메뉴, 저장/복원 경로는 그대로 유지합니다.

### Files touched in this slice

- `ui/roughcut/roughcut_major_panel.py`
- `tests/test_roughcut_ui_v2.py`
- `docs/HANDOFF.md`

### Validation run

- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py -k "minor_card_shows_subtitle_segment_count_and_snippet or five_major_cards_keep_compact_height_budget or major_log_and_title_panels_render_without_removing_legacy_table"` -> `3 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py tests/test_roughcut_candidates.py tests/test_app_command_bridge.py` -> `95 passed`
- `./venv/bin/python -m py_compile ui/roughcut/roughcut_major_panel.py tests/test_roughcut_ui_v2.py`
- `git diff --check -- ui/roughcut/roughcut_major_panel.py tests/test_roughcut_ui_v2.py docs/HANDOFF.md`

### Visual proof

- latest mockup: `output/manual_verification/latest/roughcut_vertical_columns_mockup.png`
- proof intent:
  - `LLM 후보`는 계속 `세로 기둥 3개`
  - 메인 roughcut 카드 안 `카드 세그먼트` row는 `자막 N` 배지와 실제 subtitle snippet을 같이 노출
  - 사용자는 카드 세그먼트 레벨에서 `무슨 자막 묶음인지`를 detail panel로 내리기 전에 먼저 읽을 수 있어야 함

### Remaining risk

- 오프스크린 mockup에서는 자막 개수/스니펫이 보이지만, source app 실데이터에서 자막이 길거나 조밀할 때 어느 정도까지 줄임표/생략 규칙이 필요한지는 아직 실앱으로 안 봤습니다.
- 썸네일이 없는 fixture에서는 row의 첫 인상이 여전히 텍스트 중심이라, 실사용에서 썸네일 prewarm이 더 필요한지 확인이 필요합니다.

### Recommended next step

- source app에서 roughcut fixture를 열고 `카드 세그먼트 썸네일 클릭 -> 자막 스니펫 확인 -> reorder -> 순서 재생 -> SRT export`를 한 흐름으로 확인합니다. 그때 자막 스니펫이 너무 길면 다음 조각에서 chip truncation 규칙만 좁게 손봅니다.

## 2026-06-01 Addendum - Roughcut Interaction QA Proof

### Scope

- roughcut interaction을 실앱에서 반복 검증할 수 있도록 `candidate 선택 automation`, `roughcut interaction` QA 시나리오, 그리고 oversized `status` compact projection 보강을 추가했습니다.
- 목표는 source app에서 `roughcut row 선택 -> 순서 재생 -> status 확인 -> roughcut SRT export -> snapshot`까지 한 흐름으로 증명하는 것이었습니다.
- `status` UDP compact 응답에서 `roughcut_runtime.sequence_preview_active` 같은 핵심 필드가 잘려 새 시나리오가 실패하던 문제를 닫았습니다.

### Files touched in this slice

- `core/automation/app_command_server.py`
- `tools/appctl.py`
- `tools/qa_suite_runner.py`
- `ui/main/app_command_bridge_handlers.py`
- `ui/roughcut/roughcut_widget.py`
- `tests/test_app_command_server.py`
- `tests/test_app_command_bridge.py`
- `tests/test_qa_suite_runner.py`
- `docs/HANDOFF.md`

### Validation run

- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_server.py tests/test_app_command_bridge.py tests/test_qa_suite_runner.py` -> `95 passed`
- `./venv/bin/python -m py_compile core/automation/app_command_server.py tools/appctl.py tools/qa_suite_runner.py ui/main/app_command_bridge_handlers.py ui/roughcut/roughcut_widget.py tests/test_app_command_server.py tests/test_app_command_bridge.py tests/test_qa_suite_runner.py`
- `git diff --check -- core/automation/app_command_server.py tools/appctl.py tools/qa_suite_runner.py ui/main/app_command_bridge_handlers.py ui/roughcut/roughcut_widget.py tests/test_app_command_server.py tests/test_app_command_bridge.py tests/test_qa_suite_runner.py docs/HANDOFF.md`
- `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py major` -> `failed_count=0`, artifact `output/manual_verification/latest/qa_suite_major_20260601_020448`

### Visual and artifact proof

- interaction scenario summary:
  - `output/manual_verification/latest/qa_suite_major_20260601_020448/roughcut_interaction_macau/summary.json`
- exported roughcut SRT:
  - `output/manual_verification/latest/qa_suite_major_20260601_020448/roughcut_interaction_macau/exports/roughcut_interaction_export.srt`
- interaction snapshot:
  - `output/manual_verification/latest/qa_suite_major_20260601_020448/roughcut_interaction_macau/snapshots/roughcut_interaction.png`
- proven facts from the scenario:
  - `roughcut-play-sequence` 이후 `sequence_preview_active == true`
  - compact `status` 응답에서도 `roughcut_runtime.sequence_preview_active == true`
  - `roughcut-export-srt`가 실제 파일을 생성했고 `subtitle_count == 45`
  - Macau fixture 기준 `visible_segment_ids == [A, C, B, D]`와 `order_summary == 카드 1/4 · A > C > B > D`가 실앱 status payload에 남음

### Remaining risk

- 이번 source-app proof는 `row 선택 -> 순서 재생 -> export`까지는 닫았지만, 실제 사람 손 기준 `카드 세그먼트 썸네일 클릭`과 `drag and drop` 제스처 자체를 UI 조작으로 직접 캡처한 건 아닙니다.
- Macau fixture는 현재 `candidate_count == 1`이라 새 `roughcut-select-candidate` automation을 실앱에서 다후보 상태로 증명하진 못했습니다.

### Recommended next step

- 다후보 roughcut fixture를 준비해 `roughcut-select-candidate -> row 선택 -> 순서 재생 -> export`를 한 번 더 돌립니다. 그 다음엔 실제 UI 제스처 캡처로 `썸네일 클릭`과 `drag and drop`을 source app에서 직접 남기면 roughcut 완성 증빙이 더 강해집니다.

## 2026-06-01 Addendum - Roughcut Multi-Candidate QA Proof

### Scope

- suite 전용 Macau project copy에 roughcut candidate를 하나 더 주입해 `candidate_count > 1` 상태를 source app에서 실증했습니다.
- `roughcut-select-candidate` automation과 compact `status` projection을 이용해, 다후보 상태에서 실제 선택 candidate가 바뀌고 `candidate_state`, `order_summary`가 따라 바뀌는지 확인했습니다.
- 이 조각은 원본 Macau project를 건드리지 않고 `output/manual_verification/latest/.../_suite_fixtures` 사본만 사용합니다.

### Files touched in this slice

- `tools/qa_suite_runner.py`
- `tests/test_qa_suite_runner.py`
- `docs/HANDOFF.md`

### Validation run

- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_qa_suite_runner.py tests/test_app_command_bridge.py tests/test_app_command_server.py` -> `95 passed`
- `./venv/bin/python -m py_compile tools/qa_suite_runner.py tests/test_qa_suite_runner.py`
- `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py major` -> `failed_count=0`, artifact `output/manual_verification/latest/qa_suite_major_20260601_021538`

### Visual and artifact proof

- candidate scenario summary:
  - `output/manual_verification/latest/qa_suite_major_20260601_021538/roughcut_candidate_macau/summary.json`
- candidate scenario snapshot:
  - `output/manual_verification/latest/qa_suite_major_20260601_021538/roughcut_candidate_macau/snapshots/roughcut_candidate_selected.png`
- generated multicandidate fixture:
  - `output/manual_verification/latest/qa_suite_major_20260601_021538/_suite_fixtures/DJI_20260217224203_0075_D_multicandidate.aissproj`
- proven facts from the scenario:
  - `status_candidate_ready` 시점에 `roughcut_runtime.candidate_count == 2`
  - `roughcut_runtime.candidate_ids == [editor_post_generation_roughcut_draft, suite_multicandidate_previous]`
  - `roughcut-select-candidate --index 1` 후 `selected_candidate_id == suite_multicandidate_previous`
  - 선택 후 `candidate_state == 이전 자막 기준`
  - 선택 후 `order_summary == 카드 1/4 · A > B > C > D`

### Remaining risk

- 이번 증빙은 candidate 선택 자체는 닫았지만, `후보 클릭`을 실제 mouse gesture로 직접 조작한 캡처는 아직 아닙니다. 현재는 app automation + snapshot 증빙입니다.
- 다후보 fixture는 suite용 synthetic copy라, 실제 사용자가 여러 후보를 저장한 프로젝트에서도 같은 candidate column UX가 유지되는지 한 번 더 보는 게 좋습니다.

### Recommended next step

- source app에서 실제 mouse click 기준으로 `후보 기둥 클릭`과 `카드 세그먼트 썸네일 클릭`, 가능하면 `drag and drop`까지 직접 캡처합니다. 그때 candidate 변경 후 `이전 자막 기준` 배지와 순서 요약이 바로 바뀌는지 함께 남깁니다.

## 2026-06-01 Addendum - Roughcut Live Candidate Click Probe

### Scope

- 최신 repo source app를 직접 `./venv/bin/python main.py`로 띄운 뒤, real UI 기준으로 `LLM 후보 세로 기둥 클릭`이 실제 화면과 runtime status에 함께 반영되는지 확인했습니다.
- 이 과정에서 `/Applications/AI Subtitle Studio.app` 구버전이 아니라 repo source app를 살아 있는 TTY 세션으로 띄워야 `appctl`과 Computer Use가 같은 프로세스를 안정적으로 바라본다는 점도 확인했습니다.
- `drag and drop`도 같은 화면에서 바로 시도했지만, 현재는 포커스/선택은 움직여도 `order_summary` 자체는 바뀌지 않아 direct gesture proof로는 아직 부족합니다.

### Files touched in this slice

- `docs/HANDOFF.md`

### Validation run

- `./venv/bin/python tools/appctl.py ping` -> `ok=true`
- `./venv/bin/python tools/appctl.py status` -> `current_work_mode=roughcut`, `candidate_count=2`
- `./venv/bin/python tools/appctl.py open-project output/manual_verification/latest/qa_suite_major_20260601_021538/_suite_fixtures/DJI_20260217224203_0075_D_multicandidate.aissproj`
- `./venv/bin/python tools/appctl.py start-current-roughcut`
- `./venv/bin/python tools/appctl.py open-roughcut`
- Computer Use로 첫 후보 기둥을 실제 클릭한 뒤 `./venv/bin/python tools/appctl.py status` 재확인
- `./venv/bin/python tools/appctl.py capture-snapshot output/manual_verification/latest/roughcut_live_candidate_click_20260601.png`

### Visual and artifact proof

- live click snapshot:
  - `output/manual_verification/latest/roughcut_live_candidate_click_20260601.png`
- live status after candidate click:
  - `selected_candidate_id == editor_post_generation_roughcut_draft`
  - `candidate_count == 2`
  - `filter_summary == 표시 45 / 전체 45`
  - `order_summary == 카드 3/4 · A > C > B > D`
  - `visible_segment_ids == [A, C, B, D]`
- Computer Use 화면상에서도 첫 후보 기둥 체크 상태와 `LLM 카드 4 / 세그먼트 45 / 검토 0 선택 B_0014` 화면으로 전환되는 것을 확인했습니다.

### Remaining risk

- live click은 닫았지만 `candidate_state` 라벨은 `selected_candidate_id == editor_post_generation_roughcut_draft` 상태에서도 여전히 `이전 자막 기준`으로 남습니다. 현재는 status와 UI가 함께 그렇게 보이므로, label semantics가 의도인지 stale state인지 한 번 더 판단해야 합니다.
- `drag and drop`는 Computer Use 좌표 drag를 시도했지만 `order_summary == 카드 3/4 · A > C > B > D`가 유지됐습니다. 즉 direct drag gesture proof는 아직 미완료입니다.
- `카드 세그먼트 썸네일 클릭 재생`도 이번 slice에서는 별도 직접 캡처하지 못했습니다.

### Recommended next step

- `candidate_state`가 실제 selected candidate 기준 문구인지, 아니면 기준 자막 비교 상태를 뜻하는 별도 라벨인지 owner 코드에서 먼저 정리합니다.
- 그 다음 source app에서 `카드 세그먼트 썸네일 클릭 재생`과 `drag and drop`를 다시 직접 시도하고, 실패 시에는 현재 `RoughcutMajorPanel` drag/drop surface가 Computer Use 좌표 drag를 왜 못 받는지 accessibility hit area를 좁혀서 점검합니다.

## 2026-06-01 Addendum - Roughcut Five-Card Layout Pass

### Scope

- 러프컷 첫 화면을 `좌측 카드 5줄 전후`, `좌측 하단 분리 프레임 없음`, `우측 상단 비디오 플레이어 + 그 아래 모든 메뉴` 구조로 다시 압축했습니다.
- 핵심은 `LLM 카드` 밀도를 높이면서도 `썸네일 클릭 재생`, `카드 세그먼트 drag and drop`, `우측 순서 재생/분석/검증/저장` 기능을 그대로 유지하는 것이었습니다.
- 비선택 카드는 더 얇게, 선택 카드는 약간만 확장되도록 고정 높이와 `sizeHint`를 같이 맞춰서 실제 리스트에서도 5카드 밀도가 유지되게 했습니다.

### Files touched in this slice

- `ui/roughcut/roughcut_major_panel.py`
- `ui/roughcut/roughcut_widget.py`
- `tests/test_roughcut_ui_v2.py`

### Validation run

- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py tests/test_app_command_bridge.py` -> `88 passed`
- `./venv/bin/python -m py_compile ui/roughcut/roughcut_major_panel.py ui/roughcut/roughcut_widget.py tests/test_roughcut_ui_v2.py`
- `git diff --check -- ui/roughcut/roughcut_major_panel.py ui/roughcut/roughcut_widget.py tests/test_roughcut_ui_v2.py`

### Notes

- `tests/test_roughcut_ui_v2.py`에 `5카드 높이 예산` 검증을 추가했습니다. 이 테스트는 리스트 `item.sizeHint()`까지 확인해서 카드가 다시 세로로 부풀지 않도록 막습니다.
- 오프스크린 렌더 기준으로 좌측은 `LLM 카드 5개`가 한 화면에 들어오고, 우측은 `비디오 플레이어`, `플레이어 아래 메뉴`, `러프컷 상세/탭`이 한 컬럼으로 유지됩니다.

### Remaining risk

- 현재 증빙은 오프스크린 렌더와 pytest 기준입니다. source app 실앱에서 같은 레이아웃이 `티니핑` 같은 실제 5카드 fixture에서도 그대로 보이는지 한 번 더 확인해야 합니다.
- 카드가 6개 이상일 때는 의도대로 스크롤로 넘어가지만, 대표님이 원하는 최종 밀도에 맞춰 카드 패딩/폰트가 한 번 더 줄 수 있습니다.

### Recommended next step

- source app에서 roughcut fixture를 열고 `5카드 화면`, `카드 drag and drop`, `썸네일 클릭 재생`, `우측 순서 재생`을 실제 UI로 다시 확인합니다. 그다음 필요하면 `비선택 카드에서 남길 최소 정보`만 더 줄여서 한 번 더 밀도 조정합니다.

## 2026-06-01 Addendum - Roughcut Live LLM Cards And Segment Reorder Proof

### Scope

- roughcut UI를 `LLM 카드 + 카드 세그먼트 + 우측 actual player` 기준으로 실앱에서 다시 닫았습니다.
- placeholder 한 장 상태가 아니라 실제 LLM roughcut을 source app에서 다시 돌려 `중분류 4개` 결과를 띄웠고, 그 상태에서 `카드 세그먼트(B)`를 아래로 이동시키는 자동화 owner surface를 추가했습니다.
- 목표는 대표님이 원하신 `러프컷 LLM이 자른 구역을 카드로 보고`, `우측 player는 유지한 채`, `카드 순서 변경이 state/export까지 따라가는지`를 실제 source app에서 증빙하는 것이었습니다.

### Files touched in this slice

- `ui/roughcut/roughcut_widget.py`
- `ui/main/app_command_bridge_handlers.py`
- `tools/appctl.py`
- `tests/test_app_command_bridge.py`
- `tests/test_roughcut_ui_v2.py`
- `docs/HANDOFF.md`

### What changed

- `roughcut-select-chapter` runtime snapshot에 `selected_segment_id`, `visible_segment_ids`, `segment_order`를 추가했습니다.
- `roughcut-move-segment` 자동화 명령을 새로 추가했습니다.
  - 현재 선택한 chapter가 속한 LLM 카드 세그먼트를 기준으로 위/아래 이동합니다.
  - 이동 후 roughcut state, table/preview selection, EDL/SRT 계산 순서를 같은 owner path로 다시 반영합니다.
- `roughcut-export-srt`는 같은 상태에서 다시 내보내져 현재 roughcut 순서를 반영한 SRT 산출물을 남길 수 있습니다.

### Validation run

- `./venv/bin/python -m py_compile ui/roughcut/roughcut_widget.py ui/main/app_command_bridge_handlers.py tools/appctl.py tests/test_app_command_bridge.py tests/test_roughcut_ui_v2.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py tests/test_roughcut_ui_v2.py` -> `84 passed`
- source app live proof:
  - `./venv/bin/python tools/appctl.py open-project /Users/u_mo_c/Downloads/ai_subtitle_studio/projects/DJI_20260217224203_0075_D.aissproj`
  - `./venv/bin/python tools/appctl.py open-roughcut`
  - `./venv/bin/python tools/appctl.py start-current-roughcut`
  - 약 `22s` 뒤 `./venv/bin/python tools/appctl.py status` 기준 `roughcut_state.major_count == 4`
  - `./venv/bin/python tools/appctl.py roughcut-select-chapter --row 14` -> `selected_chapter_id=B_0014`, `selected_segment_id=B`, `visible_segment_ids=[A,B,C,D]`
  - `./venv/bin/python tools/appctl.py roughcut-move-segment --direction down` -> `segment_order=[A,C,B,D]`
  - `./venv/bin/python tools/appctl.py roughcut-export-srt /tmp/roughcut_automation_export_v3.srt` -> `subtitle_count=45`
- live artifact:
  - source snapshot: `/tmp/roughcut_live_source_snapshot_v4.png`
  - exported SRT: `/tmp/roughcut_automation_export_v3.srt`

### Remaining risk

- 현재 실앱 snapshot 기준으로 좌측 `LLM 카드`와 아래 `러프컷 상세/제어`는 같은 frame 안에는 묶였지만, 시각적으로는 아직 두 패널처럼 느껴집니다.
- 우측 `플레이어 아래 메뉴`는 기능상 충분하지만, 버튼 밀도와 상단 toolbar 중복이 아직 남아 있어 대표님 기준의 `한눈에 읽히는 카드 러프컷`으로는 한 번 더 정리가 필요합니다.
- 이번 live proof는 `segment_order`와 export를 닫았지만, `우측 player가 바뀐 카드 순서 체감을 얼마나 직접적으로 전달하는지`는 추가 UI 정리가 필요합니다.

### Recommended next step

- 다음 조각은 기능 추가보다 레이아웃 정리에 집중합니다.
  - 좌측 `LLM 카드`와 아래 `러프컷 상세/제어`를 더 한 덩어리처럼 보이게 시각 계층을 줄입니다.
  - 우측 `플레이어 아래 메뉴`와 상단 toolbar의 중복 액션을 정리해, primary action을 우측에 모으고 좌측은 `카드 읽기/편집` 중심으로 단순화합니다.

## 2026-06-01 Addendum - Left Cards Only / Right Player And Menus

### Scope

- 대표님 지시대로 roughcut 화면을 `좌측 카드 전용`, `우측 actual player + 모든 메뉴` 구조로 다시 정리했습니다.
- 좌측에서는 하단 frame을 제거했고, `LLM 카드`만 남겨 카드 리스트가 남은 영역을 거의 전부 사용하게 했습니다.
- 우측에서는 플레이어 아래로 action/menu, 상세 제어, 탭형 정보 패널을 모두 내렸습니다.

### Files touched in this slice

- `ui/roughcut/roughcut_widget.py`
- `ui/roughcut/roughcut_major_panel.py`
- `tests/test_roughcut_ui_v2.py`
- `docs/HANDOFF.md`

### What changed

- 좌측
  - `main_tabs`와 좌측 하단 `bottom frame`를 제거했습니다.
  - `roughcut_frame`은 이제 `major_panel` 카드 리스트만 담습니다.
  - 카드 세그먼트는 더 간결하게 줄였습니다.
    - row별 `썸네일`, `코드`, `제목`, `시간/상태`, 짧은 자막 snippet`만 남기고 별도 `대표 장면 재생` 버튼은 제거했습니다.
    - drag and drop은 그대로 유지됩니다.
- 우측
  - `bottom_panel + bottom_tabs`를 우측으로 이동했습니다.
  - 우측은 `비디오 플레이어 -> 플레이어 아래 메뉴 -> 상세/탭형 제어` 순서입니다.
  - 기존에 좌측 상단 toolbar에 있던 action 버튼은 우측 메뉴로 몰고, toolbar는 상태/필터/선택 요약 중심으로 줄였습니다.
  - `챕터`, `자막 세그먼트`, `글로벌 세그먼트`, `웨이브폼`, `EDL`, `스토리보드`, `가이드`, `로그`, `제목`, `스타일`이 모두 우측 탭형 surface에 들어갑니다.

### Validation run

- `./venv/bin/python -m py_compile ui/roughcut/roughcut_widget.py ui/roughcut/roughcut_major_panel.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py tests/test_app_command_bridge.py` -> `84 passed`
- `git diff --check -- ui/roughcut/roughcut_widget.py ui/roughcut/roughcut_major_panel.py tests/test_roughcut_ui_v2.py docs/HANDOFF.md`
- source app snapshot:
  - `/tmp/roughcut_layout_v6.png`

### Remaining risk

- 우측 하단 상세/탭 surface는 기능상 한곳에 모였지만, 아직 세로 정보량이 많습니다. 다음 조각에서 `상세`, `탭 영역`, `로그/스타일` 우선순위를 더 줄일 수 있습니다.
- LLM 카드가 여러 개일 때도 좌측에서 `최대 5장 체감`으로 읽히는지는 fixture 길이에 따라 달라질 수 있으므로, 카드 padding과 segment row height를 조금 더 미세조정할 여지가 있습니다.

### Recommended next step

- 다음은 기능 변경 없이 카드 밀도만 더 다듬습니다.
  - 좌측 카드 padding/행 높이를 한 번 더 줄여 `5장 전후가 첫 화면에서 더 안정적으로 읽히게` 조정합니다.
  - 우측 하단 surface는 `상세` 기본 탭과 `로그/제목/스타일` 보조 탭의 시각 우선순위를 더 분명하게 나눕니다.

## 2026-06-01 Addendum - Card Density Tightening

### Scope

- `좌측 카드 전용 / 우측 player+menus` 구조는 유지한 채, 좌측 카드가 더 많은 장수를 한 화면에서 읽히도록 밀도를 한 번 더 줄였습니다.
- 목적은 대표님 요청인 `세로로 여러 카드가 한 번에 읽히는 roughcut frame`에 더 가깝게 만드는 것입니다.

### Files touched in this slice

- `ui/roughcut/roughcut_major_panel.py`
- `docs/HANDOFF.md`

### What changed

- major card 전체 높이를 더 줄였습니다.
- 카드 meta row에서 긴 tags 노출을 제거했습니다.
- 요약은 한 줄 높이에 가까운 compact text로 줄였습니다.
- 카드 세그먼트 리스트는 기본적으로 내부 2행 정도만 보이게 제한하고 내부 스크롤로 넘기도록 했습니다.
- 카드 세그먼트 row도 썸네일, 코드, 제목, 시간/상태, 짧은 subtitle snippet만 남기고 더 조밀하게 줄였습니다.

### Validation run

- `./venv/bin/python -m py_compile ui/roughcut/roughcut_major_panel.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py -k 'major_log_and_title_panels_render_without_removing_legacy_table or automation_move_selected_segment_updates_segment_order or minor_card_reorder_updates_chapter_and_edl_order'` -> `3 passed`
- latest source snapshot:
  - `/tmp/roughcut_layout_v8.png`

### Remaining risk

- fixture에 따라 card summary 길이가 길면 여전히 card 높이가 조금 커질 수 있습니다.
- 대표님이 원하신 `정확히 5장 체감`에 더 가깝게 가려면 다음엔 선택된 카드만 살짝 확장하고 나머지 카드는 더 접는 방식도 검토할 수 있습니다.

### Recommended next step

- 카드 밀도는 지금 구조를 baseline으로 두고, 다음은 `selected card emphasis / unselected card compression` 여부만 판단합니다.
- `tests/test_roughcut_candidates.py`
- `tests/test_project_segment_reload.py`
- `idea.md`

### Validation run

- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_candidates.py -k "roundtrip or load_project_roughcut_state or apply_candidate_payload or payload_keeps"` -> `5 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py -k "roughcut or open_project_file"` -> `3 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py tests/test_roughcut_candidates.py tests/test_editor_roughcut_draft.py tests/test_roughcut_models_v2.py tests/test_roughcut_contract.py tests/test_roughcut_engine1.py tests/test_roughcut_major_boundary.py` -> `128 passed`
- `./venv/bin/python -m py_compile core/roughcut/models.py tests/test_roughcut_candidates.py tests/test_project_segment_reload.py`
- `git diff --check -- core/roughcut/models.py tests/test_roughcut_candidates.py tests/test_project_segment_reload.py`

### Remaining risk

- 단위/오프스크린 기준으로는 roughcut 후보/필터/선택 챕터 복원과 auto-roughcut reopen 경계가 닫혔지만, source app 실앱에서 `candidate 전환 -> filter 변경 -> chapter 선택 -> 저장 -> 재열기`를 빠르게 반복할 때도 동일하게 자연스러운지는 아직 안 봤습니다.
- 이번 복원 보강은 compact frame payload reopen 안정성을 우선 해결한 것이고, 실앱에서는 여전히 generation 직후 roughcut auto-open 타이밍과 scrub/play 혼합 체감이 마지막 확인 포인트입니다.

### Recommended next step

- source app에서 roughcut 상태가 저장된 fixture를 열고 `candidate 전환 -> safety filter 변경 -> chapter 선택 -> 저장 -> 재열기 -> roughcut 자동 진입` 순서로 한 번 더 실앱 스모크를 남깁니다. 이때 선택 챕터, 필터, 후보 상태 배지가 그대로 살아나는지와 frame shake/ghost가 없는지 같이 확인합니다.

## 2026-05-31 Addendum - Roughcut Automation Proof Path

### Scope

- roughcut 저장/재열기 경계가 단위 테스트로만 닫혀 있던 상태에서, source-app QA가 같은 흐름을 실제 명령 시퀀스로 따라갈 수 있도록 자동화 진입점을 추가했습니다.
- `tools/appctl.py`에 `open-roughcut` 명령을 추가했고, 브리지 핸들러에서 `_open_roughcut_helper()`를 직접 호출하도록 연결했습니다.
- `tools/qa_suite_runner.py`에는 `roughcut_reopen_macau` 시나리오와 step-level `expect_data` 검증을 추가해서 `current_work_mode == roughcut`를 reopen 전후로 확인할 수 있게 했습니다.
- 같은 과정에서 `major` profile source-app QA가 시나리오별 restart 직후 `status` probe에만 의존하다 readiness timeout으로 흔들리던 문제를 좁혔습니다. 이제 QA 러너는 app command server 생존 여부를 `ping`으로 먼저 확인하고, `status`는 뒤따라 확인하도록 바뀌었습니다.

### Files touched in this slice

- `tools/appctl.py`
- `ui/main/app_command_bridge_handlers.py`
- `tools/qa_suite_runner.py`
- `tests/test_app_command_bridge.py`
- `tests/test_qa_suite_runner.py`

### Validation run

- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py -k "open_roughcut or start_current_roughcut or status_command_reports_current_runtime_snapshot"` -> `3 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_qa_suite_runner.py` -> `18 passed`
- `./venv/bin/python -m py_compile tools/appctl.py tools/qa_suite_runner.py ui/main/app_command_bridge_handlers.py tests/test_app_command_bridge.py tests/test_qa_suite_runner.py`
- `git diff --check -- tools/appctl.py tools/qa_suite_runner.py ui/main/app_command_bridge_handlers.py tests/test_app_command_bridge.py tests/test_qa_suite_runner.py`
- `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py major` -> `failed_count=0`, artifact `output/manual_verification/latest/qa_suite_major_20260531_232544`
- `output/manual_verification/latest/qa_suite_major_20260531_232544/roughcut_reopen_macau/summary.json`
  - `open_project` -> `start-current-roughcut` -> `open-roughcut` -> `status_roughcut_opened` -> `save_project` -> `reopen_project` -> `status_after_reopen` 전부 `ok`
  - reopen 전후 `current_work_mode == roughcut` 검증 통과

### Remaining risk

- 새 QA 시나리오는 reopen 전후 `current_work_mode`와 roughcut runtime 진입은 검증하지만, 실제 source app에서 후보 배지/필터/선택 챕터가 모두 기대대로 보이는지까지는 아직 자동 검증하지 않습니다.
- `open-roughcut`은 현재 `_open_roughcut_helper()`에 위임하므로, roughcut 데이터가 없는 fixture에서는 `refresh_from_editor(analyze_if_missing=False)` 특성상 빈 상태를 그대로 열 수 있습니다. 그래서 실앱 proof는 반드시 roughcut이 이미 저장된 fixture로 돌려야 합니다.
- 이전 실패 artifact `qa_suite_major_20260531_232002`는 readiness timeout 회귀 기준선으로 남겨두되, 현재는 최신 `qa_suite_major_20260531_232544`가 그 blocker를 넘긴 상태입니다.

### Recommended next step

- 최신 자동화 증빙 `output/manual_verification/latest/qa_suite_major_20260531_232544/roughcut_reopen_macau/summary.json`을 기준으로, 이제 source app 수동 smoke를 `candidate 전환 -> safety filter 변경 -> chapter 선택 -> 저장 -> 재열기 -> roughcut 자동 진입` 순서로 실제 UI에서 한 번 더 남깁니다. 이때 배지/필터/선택 챕터 시각 상태와 ghost/frame shake 유무를 함께 캡처하면 roughcut 기능 완성에 더 가깝습니다.

## 2026-05-31 Addendum - Roughcut LLM Card UI

### Scope

- 대표님 피드백 기준으로 roughcut 첫 탭이 표 안의 표처럼 보이던 구성을 걷어내고, `러프컷 LLM이 자른 중분류 덩어리`를 카드형으로 먼저 읽게 재구성했습니다.
- `중분류 맵` 탭 이름도 `LLM 카드`로 바꿨고, 카드 안에서는 `덩어리 제목`, `시간 범위`, `하위 개수`, `요약`, `대표 장면`, `하위 분류 칩`이 먼저 보이게 정리했습니다.
- 추가로 `single-card` 상황에서 카드가 세로로 늘어지던 grid stretch를 잘라, 한 덩어리만 있어도 실제 카드처럼 위에서 아래로 빠르게 읽히게 밀도를 다시 조였습니다.
- 이번 조각에서는 상단 카드 영역과 하단 roughcut 제어/세부/보조 탭을 하나의 좌측 `roughcut frame` 안으로 다시 묶었고, 카드 안에 `카드 세그먼트`, `대표 장면 재생`, `자막 세그먼트`를 같이 올렸습니다.
- `LLM 카드`는 이제 카드 리스트 기준으로 정렬되고, 카드 드래그 앤 드롭 순서가 roughcut state와 table/EDL/SRT 재계산 순서에도 반영되도록 owner state를 연결했습니다.
- 그리고 실앱 host 쪽에서도 이 unified frame이 그대로 보이도록, roughcut full page를 열 때 더 이상 `page.bottom_panel`을 bottom work panel로 다시 재부착하지 않게 막았습니다. 이제 integrated roughcut page는 self-contained left frame 기준으로 보이고, 하단 분리감은 host가 다시 만드는 구조가 아니게 됐습니다.
- 추가로 roughcut 우측 컬럼 상단에 `비디오 플레이어` host를 만들고, editor의 `video_frame`를 외부 host로 잠깐 detach/restore 할 수 있는 경로를 붙였습니다. 이걸로 roughcut full page에서도 우측 상단에 actual player surface를 유지하는 다음 단계가 가능해졌습니다.

### Files touched in this slice

- `ui/roughcut/roughcut_widget.py`
- `ui/roughcut/roughcut_major_panel.py`
- `tests/test_roughcut_ui_v2.py`

### Validation run

- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py` -> `13 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py tests/test_roughcut_candidates.py -k "roughcut or candidate"` -> `18 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py tests/test_roughcut_candidates.py` -> `19 passed`
- `./venv/bin/python -m py_compile ui/home_ui.py ui/roughcut/roughcut_widget.py ui/roughcut/roughcut_major_panel.py ui/roughcut/roughcut_table.py ui/roughcut/roughcut_state.py`
- `./venv/bin/python -m py_compile ui/editor/editor_widget.py ui/home_ui.py ui/roughcut/roughcut_widget.py tests/test_roughcut_ui_v2.py`
- `./venv/bin/python -m py_compile ui/roughcut/roughcut_widget.py ui/roughcut/roughcut_major_panel.py tests/test_roughcut_ui_v2.py`
- 샘플 렌더 확인: `/tmp/roughcut_card_preview.png`
- single-card 렌더 확인: `/tmp/roughcut_card_preview_single.png`
- unified frame 렌더 확인: `/tmp/roughcut_unified_frame_preview.png`
- right video host 렌더 확인: `/tmp/roughcut_right_video_host_preview.png`

### Remaining risk

- 카드 뷰는 now major-group reading에 맞지만, 실제 fixture에서 카드 수가 많아질 때 스크롤 체감과 배지 밀도가 충분히 좋은지는 실앱에서 한 번 더 봐야 합니다.
- 하위 분류가 아주 많아질 때는 카드 안 칩/행이 길어질 수 있어, 필요하면 다음 조각에서 collapse/expand나 preview-first 압축을 넣을 수 있습니다.
- 지금 샘플은 `주제없음 / 컷경계` 단일 카드라서, 실제 LLM 결과처럼 카드가 여러 장 나올 때도 제목/배지 우선순위가 같은 체감으로 읽히는지는 fixture로 한 번 더 봐야 합니다.
- 현재 reorder는 `중분류 카드` 기준으로 state/EDL/SRT 순서에 반영되지만, 대표님이 원하시는 `세부 카드 세그먼트` 레벨 reorder까지는 아직 아닙니다. 다음 조각에서 필요하면 minor/chapter 레벨 drag-drop으로 더 내려갈 수 있습니다.
- 우측 컬럼은 이제 actual player host를 받을 수 있게 되었지만, `세부 카드 세그먼트` 순서와 완전히 결합된 preview/재생 경험은 아직 마무리되지 않았습니다. 다음 조각에서 host에 실제 editor video frame을 실앱 fixture로 붙여 보고, 순서 변경과 preview 흐름을 더 직접적으로 맞춰야 합니다.

### Recommended next step

- source app 실앱에서 representative roughcut fixture를 열고 `LLM 카드` 탭 기준으로 `candidate 전환 -> safety filter 변경 -> chapter 선택 -> 저장 -> 재열기`를 한 번 더 보면서 카드 가독성과 상태 배지 유지 여부를 같이 확인합니다.
- 그다음 단계로는 `중분류 카드 안 minor/card-segment drag-drop -> 우측 플레이어 preview 순서 -> SRT 재계산 결과`를 실제 fixture에서 한 번 더 묶어 확인합니다.

## 2026-06-01 Addendum - Roughcut Card Segment UI Pass

### Scope

- 대표님이 roughcut UI를 `카드 중심`으로 다시 보겠다고 정리해주셔서, 이번 조각은 기능을 넓히기보다 `카드 세그먼트가 메인으로 읽히는 구조`와 `우측 플레이어 아래 메뉴`를 더 분명하게 만드는 데 집중했습니다.
- 좌측 `LLM 카드`는 `덩어리 요약 -> 카드 세그먼트 -> 자막 세그먼트` 순서로 다시 읽히게 조정했고, 카드 세그먼트 박스에는 `썸네일 클릭 재생 / 드래그 앤 드롭 순서 변경` 힌트를 직접 노출했습니다.
- 우측 컬럼에는 actual player host 바로 아래 `플레이어 아래 메뉴` 프레임을 추가해서 `분석 / 검증 / 렌더`, `SRT / EDL / 가이드`, `이전 / 구간 재생 / 다음` 작업을 한 곳에 모았습니다.
- 카드 세그먼트 썸네일도 placeholder 텍스트가 아니라 chapter 기준 thumbnail lookup을 roughcut populate 경로에서 실제로 채워 넘기도록 연결했습니다. media path가 없거나 썸네일 생성이 실패하면 기존 fallback 텍스트를 유지합니다.

### Files touched in this slice

- `ui/roughcut/roughcut_widget.py`
- `ui/roughcut/roughcut_major_panel.py`
- `ui/roughcut/roughcut_table.py`
- `tests/test_roughcut_ui_v2.py`

### Validation run

- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py tests/test_roughcut_candidates.py` -> `22 passed`
- `./venv/bin/python -m py_compile ui/roughcut/roughcut_widget.py ui/roughcut/roughcut_major_panel.py ui/roughcut/roughcut_table.py tests/test_roughcut_ui_v2.py`
- 샘플 렌더 확인: `/tmp/roughcut_card_segment_menu_preview.png`

### Remaining risk

- 지금은 카드 세그먼트와 플레이어 아래 메뉴가 오프스크린 기준으로 정리된 상태이고, source app 실앱에서 actual editor video frame이 붙은 상태까지는 아직 증빙하지 않았습니다.
- minor/card-segment reorder가 owner state와 EDL/SRT 계산 순서에는 반영되지만, 대표님이 원하신 `우측 플레이어가 바뀐 순서를 바로 따라 재생`하는 체감은 실앱 fixture에서 한 번 더 묶어 확인해야 합니다.
- chapter thumbnail lookup을 populate 시점에 바로 채우므로, 카드 수가 아주 많을 때 썸네일 생성 체감이 늘어질 수 있습니다. 필요하면 다음 조각에서 lazy/visible-first 전략으로 바꿀 수 있습니다.

### Recommended next step

- source app roughcut fixture에서 `카드 세그먼트 drag-drop -> 썸네일 클릭 재생 -> 우측 플레이어 반응 -> SRT export` 순서로 실앱 smoke를 남기고, 그 결과를 기준으로 playback 순서 동기화 owner를 더 좁힙니다.

## 2026-05-31 Addendum - Dex x Jammini Delegation Tightening

### Scope

- 대표님 요청으로 `덱스`가 단순 지원 작업을 혼자 들고 있지 않도록 협업 규칙을 더 강하게 고정했습니다.
- 기본 원칙은 `non-trivial task면 simple bounded slice를 먼저 잼민이에게 위임`, `잼민이가 idle처럼 보이면 다음 safe simple slice를 바로 큐잉`, `doc sync / narrow search / status summary / shortlist / validation prep 같은 단순 작업은 잼민이 우선`입니다.
- Antigravity `ai_subtitle_studio` 대화에도 같은 규칙을 다시 주입했고, 잼민이는 현재 대기 가능 상태와 즉시 맡을 simple slices를 짧게 회신했습니다.

### Files touched in this slice

- `AGENTS.md`
- `anti_agents.md`
- `cooperation.md`
- `tools/cooperation_bootstrap.sh`
- `docs/HANDOFF.md`

### Validation run

- `bash -n tools/cooperation_bootstrap.sh`
- `git diff --check -- AGENTS.md anti_agents.md cooperation.md tools/cooperation_bootstrap.sh docs/HANDOFF.md`

### Remaining risk

- 이 규칙은 운영 규칙이라 실제 효과는 다음 non-trivial 작업에서 `덱스`가 단순 지원 조각을 계속 잼민이에게 넘기는 실행 습관으로 확인해야 합니다.
- Antigravity 쪽 응답/쿼터 상태에 따라 delegation cadence가 느려질 수 있으니, 그 경우에도 simple slices 우선 원칙은 유지하되 실제 전송 타이밍만 조절하면 됩니다.

### Recommended next step

- 다음 큰 작업부터는 `덱스`가 owner file 구현을 잡고, 동시에 `잼민이`에게 doc sync, shortlist, targeted review, validation prep 같은 단순 조각을 바로 분배하는 흐름을 기본값으로 유지합니다.

## 2026-05-31 Addendum - Jammini Delegation Queue Activated

### Scope

- 대표님 요청으로 `ACTION_ITEMS.md` 안에 explicit `Jammini Delegation Queue`를 만들고, 현재 active execution item 아래의 simple/draft-only support work를 한 번에 큐잉했습니다.
- 이 큐는 `JQ-01`부터 `JQ-06`까지이며, 전부 code-patch 없는 파일 역할 맵, review packet, 실앱 QA checklist, validation prep, doc delta draft, cleanup shortlist 같은 보조 작업으로만 구성했습니다.
- Antigravity `ai_subtitle_studio` 대화 `2aefcd7d-ab16-4cd7-a88a-1a2482046524`에도 같은 큐를 읽고 top-to-bottom으로 소비하라는 지시를 다시 보냈습니다.

### Files touched in this slice

- `ACTION_ITEMS.md`
- `AGENTS.md`
- `anti_agents.md`
- `cooperation.md`
- `docs/HANDOFF.md`

### Validation run

- `git diff --check -- ACTION_ITEMS.md AGENTS.md anti_agents.md cooperation.md docs/HANDOFF.md`

### Remaining risk

- 큐는 문서와 대화 양쪽에 실렸지만, Antigravity 응답 지연/쿼터/프로젝트 전환 상태에 따라 실제 소비 속도는 흔들릴 수 있습니다.
- queue auto-consume 예외는 simple/draft-only item에만 적용해야 하고, code-changing item은 여전히 `덱스` 리뷰 체크포인트로 다시 돌아와야 합니다.

### Recommended next step

- 다음 턴부터는 `덱스`가 직접 구현하는 동안 `잼민이`가 `ACTION_ITEMS.md`의 `Jammini Delegation Queue`를 기준으로 support slice를 계속 소모하는지 확인하고, 들어오는 `DEX_REVIEW_READY` 패킷을 즉시 `accept / revise / defer`로 처리합니다.

## 2026-06-01 Addendum - Roughcut Five-Card Vertical Density Pass

### Scope

- 대표님 요청 기준으로 roughcut full page를 다시 `좌측 카드 중심 / 우측 플레이어 + 모든 메뉴` 구조로 더 압축했습니다.
- 좌측은 `ui/roughcut/roughcut_major_panel.py`에서 `선택 카드만 조금 크게`, `비선택 카드는 요약을 접고 카드 세그먼트를 1줄만 보여주는` 밀도 패스를 넣어서 첫 화면에서 세로 `5장 전후`가 읽히도록 조정했습니다.
- 우측은 기존 unified frame 구조를 유지하되 `ui/roughcut/roughcut_widget.py`에서 컬럼 폭과 내부 margin을 더 줄여서, 메인 메뉴/사이드바를 제외한 중앙 작업 영역을 roughcut이 더 직접적으로 쓰게 맞췄습니다.

### Files touched in this slice

- `ui/roughcut/roughcut_major_panel.py`
- `ui/roughcut/roughcut_widget.py`
- `tests/test_roughcut_ui_v2.py`
- `docs/HANDOFF.md`

### Validation run

- `./venv/bin/python -m py_compile ui/roughcut/roughcut_major_panel.py ui/roughcut/roughcut_widget.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py tests/test_app_command_bridge.py` -> `84 passed`
- 스냅샷 렌더 확인: `/tmp/roughcut_layout_v9.png`

### Remaining risk

- 현재 밀도는 `선택 카드 1장 + 비선택 카드 4장` 전후 기준으로는 맞지만, 실제 LLM 결과에서 각 카드의 세그먼트 수가 더 많아지면 여전히 첫 화면 가독성이 달라질 수 있습니다.
- 지금은 `비선택 카드 압축` 위주라서, 다음 단계에서 필요하면 `선택 카드만 오른쪽 detail과 더 강하게 연동`하거나 `비선택 카드에서 meta chip 1개를 더 줄이는` 미세 조정이 가능해 보입니다.

### Recommended next step

- source app 실제 roughcut fixture에서 `/tmp/roughcut_layout_v9.png`와 비슷한 밀도가 나오는지 다시 확인하고, 카드 수가 많은 fixture 기준으로도 `좌측 5장 전후 / 우측 플레이어 아래 메뉴` 느낌이 유지되는지만 실앱으로 한 번 더 증빙합니다.

## 2026-06-01 Addendum - Roughcut Live Reorder Proof And Density SizeHint Fix

### Scope

- `projects/티니핑_유스어드벤처.aissproj`를 source app에서 다시 열어 roughcut live 상태를 확인했고, `open-roughcut -> status -> roughcut-move-segment -> roughcut-export-srt`까지 실앱으로 좁게 증빙했습니다.
- 같은 턴에서 `ui/roughcut/roughcut_major_panel.py`의 카드 압축 규칙이 실레이아웃에 덜 반영되던 원인을 좁혀서, `selected/unselected density`가 바뀔 때 `QListWidgetItem sizeHint`도 같이 다시 계산하도록 수정했습니다.
- 이 패치로 `선택 카드 1장 + 비선택 카드 4장` 구성이 오프스크린 기준으로는 실제 한 화면에 더 가깝게 붙었습니다.

### Files touched in this slice

- `ui/roughcut/roughcut_major_panel.py`
- `docs/HANDOFF.md`

### Validation run

- `./venv/bin/python -m py_compile ui/roughcut/roughcut_major_panel.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py tests/test_app_command_bridge.py` -> `85 passed`
- 오프스크린 렌더 확인: `/tmp/roughcut_layout_v10.png`
- source app live status:
  - project: `projects/티니핑_유스어드벤처.aissproj`
  - `roughcut_runtime.visible_chapter_ids` before reorder: `A, B, C, D, E`
  - `roughcut_runtime.visible_chapter_ids` after `roughcut-move-segment --direction down`: `B, A, C, D, E`
  - `video_host_attached=true`, `player_menu_visible=true`
- source app live artifacts:
  - before/5-card project snapshot: `/tmp/roughcut_live_tinyping_before.png`
  - after reorder snapshot: `/tmp/roughcut_live_tinyping_after.png`
  - export proof: `/tmp/roughcut_tinyping_after_move.srt`

### Remaining risk

- `티니핑` live proof는 카드 5개 프로젝트에서 reorder/export/player host 상태를 보여주지만, 이 스냅샷은 `sizeHint` 재계산 패치를 source process에 다시 로드하기 전 상태입니다.
- 즉 현재 최신 코드의 `더 붙은 5-card density`는 오프스크린 `/tmp/roughcut_layout_v10.png`로는 증명됐고, source app에서도 같은 결과를 보려면 앱 재시작 후 같은 `티니핑` fixture로 한 번 더 찍어야 합니다.

### Recommended next step

- source app를 최신 코드로 다시 띄운 뒤 `projects/티니핑_유스어드벤처.aissproj`에서 `/tmp/roughcut_layout_v10.png`와 비슷한 밀도로 보이는지 재촬영하고, 그 상태에서 `카드 이동 -> SRT export`를 한 번 더 묶어 현재 코드 기준 live proof를 닫습니다.

## 2026-06-01 Addendum - Player Menu Order Summary

### Scope

- reorder 이후 우측 플레이어 아래 메뉴에서도 `현재 카드가 전체 순서에서 어디인지`를 바로 읽을 수 있게 정리했습니다.
- `ui/roughcut/roughcut_widget.py`, `ui/roughcut/roughcut_table.py` 기준으로 `player_order_lbl`을 추가했고, 선택 카드가 바뀌거나 세그먼트 순서가 바뀌면 `카드 2/5 · B > A > C > D > E` 같은 요약이 바로 갱신되게 맞췄습니다.
- automation runtime snapshot에도 같은 `order_summary`를 넣어서 실앱 상태 수집 시 reorder 결과를 더 직접적으로 증명할 수 있게 했습니다.

### Files touched in this slice

- `ui/roughcut/roughcut_widget.py`
- `ui/roughcut/roughcut_table.py`
- `tests/test_roughcut_ui_v2.py`
- `tests/test_app_command_bridge.py`
- `docs/HANDOFF.md`

### Validation run

- `./venv/bin/python -m py_compile ui/roughcut/roughcut_widget.py ui/roughcut/roughcut_table.py tests/test_roughcut_ui_v2.py tests/test_app_command_bridge.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py tests/test_app_command_bridge.py` -> `85 passed`

### Remaining risk

- source app 최신 코드 재시작 후 live 상태에서 이 `order_summary`까지 직접 찍는 증빙은 아직 없습니다.
- 이번 턴에 source app restart를 두 번 시도했는데, 재기동 직후 automation attach가 불안정해서 `status/appctl`이 다시 timeout 되거나 새 프로세스가 유지되지 않는 구간이 있었습니다.

### Recommended next step

- restart 경로를 한 번 더 안정화한 뒤 `티니핑` fixture로 들어가서 `player_order_lbl`이 실제로 `카드 n/5` 형태로 갱신되는지, 그리고 `roughcut_runtime.order_summary`가 live status에도 그대로 보이는지 찍어 둡니다.

## 2026-06-01 Addendum - Ordered Preview Sequence

### Scope

- roughcut 우측 플레이어 아래 메뉴의 primary play action을 `구간 재생` 단건 재생이 아니라 `현재 roughcut 순서대로 연속 재생`으로 더 직접적으로 연결했습니다.
- `ui/roughcut/roughcut_preview.py`에 ordered sequence state를 추가해서, 선택된 row부터 visible row 순서대로 다음 챕터/카드로 자동 진행하도록 맞췄습니다.
- 이 변경으로 reorder 뒤에는 우측 메뉴의 `순서 재생`이 현재 `segment_order/chapter_order`를 따라가며, 우측 요약 라벨도 다음 row로 넘어가기 전에 먼저 갱신됩니다.

### Files touched in this slice

- `ui/roughcut/roughcut_widget.py`
- `ui/roughcut/roughcut_preview.py`
- `ui/roughcut/roughcut_table.py`
- `tests/test_roughcut_ui_v2.py`
- `tests/test_app_command_bridge.py`
- `docs/HANDOFF.md`

### Validation run

- `./venv/bin/python -m py_compile ui/roughcut/roughcut_widget.py ui/roughcut/roughcut_preview.py ui/roughcut/roughcut_table.py tests/test_roughcut_ui_v2.py tests/test_app_command_bridge.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py tests/test_app_command_bridge.py` -> `86 passed`

### Remaining risk

- ordered preview sequence는 오프스크린과 automation 테스트로는 증명됐지만, source app 최신 프로세스에서 실제 media player가 row 경계마다 자연스럽게 이어지는지는 아직 live proof가 부족합니다.
- source app restart/attach 불안정성 때문에 이번 턴에도 `티니핑` fixture 최신 코드 live proof는 닫지 못했습니다.

### Recommended next step

- restart 경로를 다시 안정화한 뒤 `티니핑` fixture에서 `순서 재생`을 실제로 눌러 `A->B->C...`처럼 넘어가는지, reorder 뒤에는 새 순서를 그대로 따라가는지 영상/스냅샷 증빙을 남깁니다.

## 2026-06-01 Addendum - Vertical Candidate Columns Live Render

### Scope

- roughcut 좌측 상단 `LLM 후보` 영역을 실제 위젯 렌더 기준으로 다시 확인했고, `세로로 긴 후보 기둥 3개를 좌우로 병렬 배치`하는 구조를 유지했습니다.
- 각 후보 기둥 안에는 roughcut 세그먼트가 `위에서 아래로` 수직 적재되고, 현재 선택 후보만 강조되도록 유지됩니다.
- 이번 턴에는 mockup이 아니라 현재 코드로 실제 `RoughcutWidget`를 렌더해서 캡처를 남겼습니다.

### Files touched in this slice

- `ui/roughcut/roughcut_widget.py`
- `ui/roughcut/roughcut_major_panel.py`
- `tests/test_roughcut_ui_v2.py`
- `docs/HANDOFF.md`

### Validation run

- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py -k 'candidate_state_and_filter_badges_follow_selection or candidate_preview_frames_limit_to_three_and_apply_selection or drag_handles_exist_for_major_and_minor_cards'` -> `3 passed, 21 deselected`
- `./venv/bin/python -m py_compile ui/roughcut/roughcut_widget.py ui/roughcut/roughcut_major_panel.py tests/test_roughcut_ui_v2.py`
- live render artifact: `output/manual_verification/latest/roughcut_vertical_columns_live_20260601.png`

### Remaining risk

- 오프스크린 live render에서는 후보 기둥 3개 배치가 맞지만, source app 실앱에서 같은 밀도로 보이는지까지는 이번 턴에 다시 찍지 않았습니다.
- 후보 기둥 안 정보 밀도는 아직 과할 수 있어서, 비선택 기둥에서 꼭 남길 정보 3개만 보이는 형태로 한 번 더 다이어트할 여지가 있습니다.

### Recommended next step

- source app multicandidate fixture에서 실제 `후보 기둥 클릭 -> 세그먼트 확인 -> 썸네일 재생`을 한 번 더 찍고, 비선택 기둥 정보량을 `후보 이름 / 자막 기준 / 세그먼트 요약` 정도로 더 줄일지 결정합니다.

## 2026-06-01 Addendum - Candidate Column Toggle Fix and Live Proof

### Scope

- source app live roughcut에서 `LLM 후보` 세로 기둥을 Computer Use로 클릭했을 때, check state만 바뀌고 실제 `selected_candidate_id`가 따라오지 않던 경로를 좁게 수정했습니다.
- 원인은 후보 기둥이 `checkable QPushButton`인데 `clicked`만 연결되어 있어서, 접근성/체크박스 스타일 토글 경로에서는 선택 적용이 빠질 수 있던 점이었습니다.
- `ui/roughcut/roughcut_widget.py`에서 후보 기둥에 `toggled` 경로도 연결했고, `tests/test_roughcut_ui_v2.py`에 toggle 기반 보호 테스트를 추가했습니다.

### Files touched in this slice

- `ui/roughcut/roughcut_widget.py`
- `tests/test_roughcut_ui_v2.py`
- `docs/HANDOFF.md`

### Validation run

- `./venv/bin/python -m py_compile ui/roughcut/roughcut_widget.py tests/test_roughcut_ui_v2.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py -k 'candidate_state_and_filter_badges_follow_selection or candidate_preview_frames_limit_to_three_and_apply_selection or candidate_preview_toggle_applies_selection or drag_handles_exist_for_major_and_minor_cards'` -> `4 passed, 21 deselected`
- source app live proof:
  - multicandidate fixture reopen 후 Computer Use로 `이전 후보 1` 기둥 클릭
  - runtime status: `selected_candidate_id == suite_multicandidate_previous`
  - 이어서 `자막 생성 후 초안` 기둥 내부 세그먼트 클릭
  - runtime status: `selected_candidate_id == editor_post_generation_roughcut_draft`, `selected_chapter_id == B_0014`, `selected_segment_id == B`, `order_summary == 카드 3/4 · A > C > B > D`
- artifacts:
  - widget snapshot: `output/manual_verification/latest/roughcut_candidate_click_fixed_widget_20260601.png`
  - status snapshot: `output/manual_verification/latest/roughcut_candidate_click_fixed_20260601_status.json`
  - full-screen capture: `output/manual_verification/latest/roughcut_candidate_click_fixed_20260601.png`

### Remaining risk

- 후보 기둥 클릭/세그먼트 선택은 live proof가 닫혔지만, `drag and drop` 자체는 Computer Use 좌표 드래그 기준으로 아직 `order_summary` 변경 증빙이 없습니다.
- 현재는 리스트/핸들 owner와 테스트는 갖춰졌고, 실제 source app에서 drag gesture가 왜 먹지 않는지만 추가로 좁혀야 합니다.

### Recommended next step

- source app multicandidate 상태에서 `drag handle` hit area를 더 키우거나, 실제 `QListWidget` drag start가 mouse path에서 어떻게 막히는지 owner logging을 붙여서 `drag -> order_summary 변경` live proof를 닫습니다.

## 2026-06-01 Addendum - Drag Reorder Live Proof

### Scope

- major card reorder를 Qt internal drag/drop에만 기대지 않도록, `card surface`와 `row surface`의 실제 세로 드래그 제스처를 직접 reorder delta로 해석하는 fallback을 추가했습니다.
- `ui/roughcut/roughcut_major_panel.py`에서 major/minor surface와 handle이 vertical drag delta를 내보내고, 그 delta를 현재 순서에 바로 적용하도록 owner 경로를 보강했습니다.
- 이 변경으로 source app 실앱에서도 Computer Use 마우스 드래그만으로 `order_summary`와 후보 기둥 내부 세그먼트 순서가 실제로 바뀌는 것을 증명했습니다.

### Files touched in this slice

- `ui/roughcut/roughcut_major_panel.py`
- `tests/test_roughcut_ui_v2.py`
- `docs/HANDOFF.md`

### Validation run

- `./venv/bin/python -m py_compile ui/roughcut/roughcut_major_panel.py tests/test_roughcut_ui_v2.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py -k 'drag_handles_exist_for_major_and_minor_cards or drag_surfaces_emit_major_and_minor_reorder_requests or candidate_preview_toggle_applies_selection'` -> `3 passed, 23 deselected`
- source app live proof:
  - multicandidate previous 후보 상태에서 첫 카드 surface를 아래로 드래그
  - runtime status after drag:
    - `selected_candidate_id == suite_multicandidate_previous`
    - `selected_chapter_id == A_0000`
    - `selected_segment_id == A`
    - `order_summary == 카드 3/4 · B > C > A > D`
    - `visible_segment_ids == [B, C, A, D]`

### Artifacts

- widget snapshot after drag reorder: `output/manual_verification/latest/roughcut_drag_reorder_fixed_widget_20260601.png`
- full-screen capture after drag reorder: `output/manual_verification/latest/roughcut_drag_reorder_fixed_20260601.png`
- status snapshot after drag reorder: `output/manual_verification/latest/roughcut_drag_reorder_fixed_20260601_status.json`

### Remaining risk

- major card reorder live proof는 닫혔지만, `minor/chapter row` 드래그를 같은 방식으로 source app에서 별도 증명하진 않았습니다.
- current roughcut objective 기준으로는 후보 기둥 클릭과 major card reorder가 핵심 축을 닫았고, 다음 남은 검증은 chapter-level reorder와 ordered preview/export가 그 순서를 그대로 따라가는지 더 직접적으로 남기는 쪽입니다.

### Recommended next step

- `minor row` surface를 실제로 위/아래로 드래그해서 `selected_chapter_id`와 `chapter_order`가 바뀌는지 찍고, 이어서 `순서 재생`과 `SRT export`가 새 chapter 순서를 그대로 반영하는지까지 묶어서 남깁니다.

## 2026-06-01 Addendum - Direct Minor Row Drag Proof

### Scope

- source app multicandidate roughcut 상태에서 `minor/chapter row`를 실제 마우스 드래그로 위로 이동시키고, automation status가 그 reorder를 즉시 반영하는지 닫았습니다.
- 이번 증빙은 `roughcut-move-chapter` 같은 우회 명령이 아니라 실제 row surface drag를 사용했고, 그 뒤 `roughcut-select-chapter`, `roughcut-play-sequence`, `roughcut-export-srt`까지 같은 reorder 상태에서 다시 확인했습니다.

### Validation run

- direct drag gesture on source app:
  - selected draft candidate `editor_post_generation_roughcut_draft`
  - selected chapter `B_0015`
  - dragged the visible `B2` row upward on the expanded `B` card surface
  - runtime converged to:
    - `selected_chapter_id == B_0015`
    - `selected_segment_id == B`
    - `chapter_order == [B_0015, B_0014, B_0016, ...]`
    - `visible_chapter_ids` also started with `B_0015, B_0014, B_0016`
- follow-up proof on the same reordered state:
  - `./venv/bin/python tools/appctl.py roughcut-select-chapter --chapter-id B_0015`
  - `./venv/bin/python tools/appctl.py roughcut-play-sequence`
  - `./venv/bin/python tools/appctl.py roughcut-export-srt output/manual_verification/latest/roughcut_minor_drag_export_20260601.srt`

### Artifacts

- direct drag snapshot before follow-up actions: `output/manual_verification/latest/roughcut_minor_drag_attempt_after1_20260601.png`
- direct drag reordered state as command result: `output/manual_verification/latest/roughcut_minor_drag_direct_reselected_20260601.json`
- direct drag status snapshot while preview was active: `output/manual_verification/latest/roughcut_minor_drag_direct_20260601_status.json`
- export after direct drag reorder: `output/manual_verification/latest/roughcut_minor_drag_export_20260601.srt`

### Remaining risk

- `minor row` direct drag는 이제 live proof가 닫혔지만, 그 순간의 전체화면 캡처는 row label만으로 reorder가 눈에 아주 명확히 읽히진 않습니다. 현재는 runtime/status artifact가 reorder를 수치로 증명하는 형태가 더 강합니다.
- `candidate_state == 이전 자막 기준`은 여전히 현재 project subtitle signature와 draft candidate signature mismatch 때문에 유지됩니다. 지금 기준으로는 stale bug가 아니라 의미상 일치입니다.

### Recommended next step

- if visual proof needs to be even more obvious, attach a small in-app reorder badge or transient toast on chapter drag so that future snapshots read the chapter swap at a glance.
- otherwise the remaining work can shift from proof to polish: tighten roughcut card density, candidate-state wording, and any final UX cleanup around the player-side menu.

## 2026-06-01 Addendum - Reorder Badge And Candidate-State Wording Polish

### Scope

- `ui/roughcut/roughcut_widget.py`에 `재정렬 없음 / 챕터 재정렬 ... / 카드 재정렬 ...` 배지를 추가해서, chapter/segment reorder가 화면에서 바로 읽히게 했습니다.
- `이전 자막 기준` 문구는 `저장된 자막 기준`으로 정리했습니다. 의미는 동일하지만, 현재 자막과 다를 때 왜 stale처럼 보이는지 덜 헷갈리게 하는 방향입니다.
- candidate 교체 시 이전 reorder 문구가 남지 않도록 `ui/roughcut/roughcut_state.py`, `ui/roughcut/roughcut_table.py`에서 reorder badge reset도 같이 넣었습니다.

### Files touched in this slice

- `ui/roughcut/roughcut_widget.py`
- `ui/roughcut/roughcut_state.py`
- `ui/roughcut/roughcut_table.py`
- `tests/test_roughcut_ui_v2.py`

### Validation run

- `./venv/bin/python -m py_compile ui/roughcut/roughcut_widget.py ui/roughcut/roughcut_state.py ui/roughcut/roughcut_table.py tests/test_roughcut_ui_v2.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py -k 'minor_card_reorder_updates_chapter_and_edl_order or candidate_state_and_filter_badges_follow_selection or candidate_preview_toggle_applies_selection'` -> `3 passed`
- `git diff --check -- ui/roughcut/roughcut_widget.py ui/roughcut/roughcut_state.py ui/roughcut/roughcut_table.py tests/test_roughcut_ui_v2.py` passed

### Fresh runtime observation after source-app restart

- source app를 재기동한 뒤 multicandidate fixture를 다시 열어보니, 새 문구(`저장된 자막 기준`) 자체는 runtime command 결과에서 확인됐습니다.
- 하지만 `open-project -> open-roughcut -> roughcut-select-candidate(editor_post_generation_roughcut_draft)` 직후에는 다시 `topicless A 1행`처럼 보이는 restore/candidate convergence 경계가 남아 있습니다.
- 같은 세션에서 `suite_multicandidate_previous`는 다시 45행 상태로 보이는 반면, global `status`는 곧바로 draft candidate 1행 상태로 되돌아가는 순간이 있었습니다.

### Remaining risk

- reorder badge/polish는 들어갔지만, restart 직후 multicandidate roughcut에서 draft candidate restore가 다시 `1 visible row`로 축소되는 경계가 아직 남아 있습니다.
- roughcut objective 관점에서 다음 우선순위는 이 convergence/restore 경계를 다시 닫는 것입니다. 지금은 UI polish보다 이 경계가 기능 완성도에 더 직접적으로 걸립니다.

### Recommended next step

- `open-project -> open-roughcut -> candidate select` 이후 어떤 owner가 `_result`, `_row_chapter_ids`, `_selected_candidate_id`를 다시 덮는지 좁힙니다.
- `editor_post_generation_roughcut_draft`와 `suite_multicandidate_previous`를 restart 후에도 같은 수준으로 복원하는 regression test를 추가하고, source-app에서 45행/4카드 상태까지 다시 실증합니다.

## 2026-06-01 Addendum - Approved Candidate Column Baseline

### Scope

- 대표님 승인 기준으로 `LLM 후보` 영역을 `좁고 긴 세로 기둥 3개를 좌우 병렬 배치`하는 baseline으로 다시 못 박았습니다.
- 각 후보 기둥 안에는 roughcut 세그먼트를 `위에서 아래로`만 쌓고, 후보 영역 설명 문구도 같은 의미로 맞췄습니다.
- 이 변경은 roughcut 후보 프레임의 배치/비율만 더 명확히 한 것이고, 후보 클릭/저장/복원 로직은 그대로 유지했습니다.

### Files touched in this slice

- `ui/roughcut/roughcut_widget.py`

### Validation run

- `./venv/bin/python -m py_compile ui/roughcut/roughcut_widget.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py -k 'candidate_state_and_filter_badges_follow_selection or candidate_preview_frames_limit_to_three_and_apply_selection or candidate_preview_toggle_applies_selection'` -> `3 passed`
- `git diff --check -- ui/roughcut/roughcut_widget.py` passed

### Visual baseline artifact

- latest approved mockup: `output/manual_verification/latest/roughcut_vertical_columns_mockup.png`

### Recommended next step

- 이 후보 기둥 baseline은 유지한 채, source app에서 multicandidate fixture를 열어 `후보 기둥 클릭 -> 세그먼트 확인 -> reorder/preview`만 다시 실제로 확인합니다.

## 2026-06-01 Addendum - Restart Restore Uses Selected Stale Candidate

### Scope

- multicandidate roughcut reopen이 `topicless 1행`으로 축소되던 핵심 원인을 `source_signature mismatch`로 좁혔습니다.
- 실제 fixture를 읽어보면 editor reopen signature는 `027c...`인데 saved candidate signatures는 `6d5d...` / `6d5d...-previous`라서, 기존 로직은 아무 candidate도 매치하지 못하고 placeholder 경로로 빠지고 있었습니다.
- 이를 막기 위해 exact signature match가 없을 때는 `selected_candidate_id`가 가리키는 saved candidate를 stale 상태로라도 우선 복원하게 바꿨습니다.

### Files touched in this slice

- `ui/roughcut/roughcut_state.py`
- `tests/test_roughcut_candidates.py`

### Validation run

- `./venv/bin/python -m py_compile ui/roughcut/roughcut_state.py tests/test_roughcut_candidates.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_candidates.py -k 'load_project_roughcut_state or restores_saved_candidate_filter_and_selection_after_project_roundtrip or stale_signature'` -> `3 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_project_segment_reload.py -k 'roughcut'` -> `2 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py -k 'roughcut_select_candidate or open_roughcut'` -> `2 passed`
- `git diff --check -- ui/roughcut/roughcut_state.py tests/test_roughcut_candidates.py` passed

### Fixture proof

- direct widget reopen against `output/manual_verification/latest/qa_suite_major_20260601_030041/_suite_fixtures/DJI_20260217224203_0075_D_multicandidate.aissproj` now restores:
  - `selected_candidate_id = suite_multicandidate_previous`
  - `candidate_state = 저장된 자막 기준`
  - `row_count = 45`
  - `chapter_count = 45`
  - `segment_count = 4`
  - `order_summary = 카드 1/4 · A > B > C > D`

### Remaining risk

- this turn proved the reopen path at widget/fixture level, but latest-code source-app automation proof did not close because the freshly restarted `main.py` process exited before appctl readiness stabilized.
- old running source app before restart was still showing the pre-fix `1행` runtime, so do not use that as current evidence anymore.

### Recommended next step

- relaunch source app from the updated tree and re-run:
  - `open-project ...DJI_20260217224203_0075_D_multicandidate.aissproj`
  - `status`
  - confirm `visible_row_count == 45`, `candidate_count == 2`, `selected_candidate_id == suite_multicandidate_previous`
- after that, continue to the same live path with `후보 기둥 클릭 -> reorder/preview/export`.

### Extra regression added after this slice

- `tests/test_roughcut_candidates.py`에서 stale-signature / roundtrip 복원 뒤 `refresh_from_editor(analyze_if_missing=False)`를 한 번 더 호출해도,
  - `selected_candidate_id`
  - `candidate_state`
  - restored chapter/title
  가 그대로 유지되는지까지 추가로 확인했습니다.
- 즉 지금 회귀는 `한 번 복원 성공`뿐 아니라 `복원 직후 추가 refresh`에서도 placeholder로 다시 무너지지 않는 경계까지 포함합니다.

## 2026-06-01 Addendum - Source-App Automation Thread Recovery And Live Multicandidate Proof

### Scope

- source app가 `127.0.0.1:47291`에 bind된 채 `appctl ping/status`만 timeout 나던 원인을 `LocalAppCommandServer` listener thread 유실로 좁혔습니다.
- `core/automation/app_command_server.py`에서 dead thread를 다시 시작할 수 있게 `start()`를 보강했고,
- `main.py`에서는 `QTimer` keepalive를 붙여 listener thread가 transient recv error 뒤 죽어도 2초 안에 다시 살아나게 했습니다.

### Files touched in this slice

- `core/automation/app_command_server.py`
- `main.py`
- `tests/test_app_command_server.py`

### Validation run

- `./venv/bin/python -m py_compile core/automation/app_command_server.py main.py tests/test_app_command_server.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_server.py` -> `9 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_app_command_bridge.py -k 'guided_subtitle_status or open_roughcut or roughcut_select_candidate'` -> `3 passed`
- `git diff --check -- core/automation/app_command_server.py main.py tests/test_app_command_server.py` passed

### Live source-app proof

- 기존 `/Applications/AI Subtitle Studio.app`를 내리고 최신 트리의 `./venv/bin/python main.py`를 직접 실행한 뒤,
  - `./venv/bin/python tools/appctl.py ping`
  - `./venv/bin/python tools/appctl.py status`
  가 즉시 `ok=true`로 돌아오는 것을 확인했습니다.
- 이어서 multicandidate fixture
  - `output/manual_verification/latest/qa_suite_major_20260601_030041/_suite_fixtures/DJI_20260217224203_0075_D_multicandidate.aissproj`
  를 `open-project -> open-roughcut`으로 열었을 때 live runtime이 다음 값으로 복원됐습니다.
  - `selected_candidate_id = suite_multicandidate_previous`
  - `candidate_count = 2`
  - `visible_row_count = 45`
  - `visible_segment_ids = [A, B, C, D]`
  - `order_summary = 카드 1/4 · A > B > C > D`
- 같은 세션에서 `roughcut-select-candidate --candidate-id editor_post_generation_roughcut_draft`도 live로 성공했고,
  - `selected_candidate_id = editor_post_generation_roughcut_draft`
  - `selected_chapter_id = B_0014`
  - `order_summary = 카드 3/4 · A > C > B > D`
  - `visible_row_count = 45`
  로 수렴했습니다.
- 이어서 `roughcut-play-sequence`까지 성공했고, 이후 `status`에서
  - `sequence_preview_active = true`
  - `video_playback_state = playing`
  - `selected_chapter_id = B_0016`
  를 확인했습니다.

### Artifacts

- live snapshot queue result:
  - `output/manual_verification/latest/roughcut_restart_restore_live_20260601.png`

### Remaining risk

- `capture-snapshot` 직후 한 번은 stale status cache를 밟아 `roughcut_runtime`가 비어 보일 수 있었지만, 1초 후 재조회에서는 정상 runtime으로 복귀했습니다.
- 즉 transport/appctl은 살아났고, 지금 남은 건 기능 고장보다 `snapshot/status timing` 쪽의 관찰 노이즈입니다.

### Recommended next step

- 이 live baseline 위에서 바로 `drag and drop`, `candidate click`, `thumbnail preview`, `roughcut-export-srt`를 한 흐름으로 다시 캡처합니다.
- transport 복구는 끝났으므로, 다음부터는 `/Applications` bundle이 아니라 최신 트리의 source app 기준으로만 roughcut 실앱 proof를 쌓는 편이 안전합니다.

## 2026-06-01 Addendum - Live Preview, Reorder, And Export Proof On Recovered Source App

### Scope

- recovered source app automation 위에서 roughcut의 남은 핵심 interaction을 실제 command/artifact로 더 닫았습니다.
- 이번 턴에서 확인한 흐름은:
  - `roughcut-select-candidate`
  - `roughcut-select-chapter --autoplay`
  - `roughcut-move-chapter`
  - `roughcut-move-segment`
  - `roughcut-export-srt`
  - `capture-snapshot`

### Live proof

- draft candidate 기준으로 `roughcut-select-chapter --chapter-id B_0014 --autoplay`를 실행했고, 뒤이은 live `status`에서
  - `selected_candidate_id = editor_post_generation_roughcut_draft`
  - `selected_chapter_id = B_0014`
  - `selected_segment_id = B`
  - `visible_row_count = 45`
  - `video_playback_state = paused`
  - `video_position_ms = 62954`
  를 확인했습니다.
- autoplay preview는 현재 automation surface에서 `thumbnail click`의 직접 대체 경로로 취급할 수 있습니다. UI 쪽에서 thumbnail button은 여전히 `previewRequested(chapter_id, hover=False)`를 emit하고, automation에서는 `roughcut-select-chapter --autoplay`가 같은 preview path를 사용합니다.

- 이어서 chapter reorder를 live로 다시 확인했습니다.
  - `roughcut-move-chapter --direction down`
  - 결과:
    - `selected_chapter_id = B_0014`
    - `reorder_summary = 챕터 재정렬 · B_0015 > B_0014 > B_0016 > B_0017`
    - `visible_chapter_ids` head = `B_0015, B_0014, B_0016, ...`

- segment/card reorder도 같은 세션에서 다시 확인했습니다.
  - `roughcut-move-segment --direction up`
  - 결과:
    - `order_summary = 카드 2/4 · A > B > C > D`
    - `reorder_summary = 카드 재정렬 · A > B > C > D`
    - `visible_segment_ids = [A, B, C, D]`

### Artifacts

- live reorder snapshot:
  - `output/manual_verification/latest/roughcut_chapter_segment_reorder_20260601.png`
- chapter-reorder export:
  - `output/manual_verification/latest/roughcut_autoplay_reorder_export_20260601.srt`
- segment-reorder export:
  - `output/manual_verification/latest/roughcut_segment_reorder_export_20260601.srt`

### Notes

- export file 첫 블록 확인은 정상입니다. `roughcut_segment_reorder_export_20260601.srt`는 실제 파일 생성까지 확인했습니다.
- `capture-snapshot` 직후 1회성 `status`는 fast-path stale cache를 밟을 수 있으므로, live proof는 가능하면
  - state-changing command result payload
  - 1초 이상 지난 뒤의 follow-up `status`
  두 개를 같이 보관하는 편이 안전합니다.

### Recommended next step

- now that candidate restore, autoplay preview, chapter reorder, segment reorder, and export all have live source-app proof, the next highest-value slice is polish:
  - thumbnail click 자체를 automation/gesture로 한번 더 직접 캡처
  - export order가 reorder와 맞는지 fixture-aware assertion 추가
  - right player menu density and card information priority cleanup

### Additional regression added after this slice

- `tests/test_roughcut_ui_v2.py`에 `test_major_card_reorder_changes_exported_srt_order`를 추가했습니다.
- coverage:
  - `automation_move_selected_segment(-1)`로 major/segment order를 바꾼 뒤
  - `export_roughcut_srt_to_path(...)`
  - exported SRT에서 `둘째 카드 자막`이 `첫 카드 자막`보다 먼저 나오는지 확인합니다.
- 즉 이제 export 회귀는
  - chapter/minor reorder
  - segment/major reorder
  두 경로 모두 테스트로 잠겨 있습니다.

## 2026-06-01 Addendum - Direct Thumbnail Click Live Proof

### Scope

- roughcut major card 안의 `썸네일 클릭 재생`을 source app 실앱 gesture로 직접 다시 닫았습니다.
- 함께 `ui/roughcut/roughcut_major_panel.py`에서 minor thumbnail hit area를 키워 실제 클릭 성공률을 높였고, 보호 테스트도 추가했습니다.

### Code change

- `ui/roughcut/roughcut_major_panel.py`
  - minor thumbnail button을 `56x28`로 키웠습니다.
  - object name `roughcutMinorThumbnailButton`을 추가했습니다.
  - thumbnail icon 적용 시 버튼 전체보다 살짝 작은 `iconSize`를 써서 실제 썸네일 가독성을 유지했습니다.
- `tests/test_roughcut_ui_v2.py`
  - `test_thumbnail_button_emits_preview_request_for_minor_row`에 button object name / width / height 회귀를 추가했습니다.

### Validation

- `./venv/bin/python -m py_compile ui/roughcut/roughcut_major_panel.py tests/test_roughcut_ui_v2.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py -k 'thumbnail_button_emits_preview_request_for_minor_row or five_major_cards_keep_compact_height_budget or selected_major_card_expands_to_show_multiple_minor_rows'`
  - `3 passed`
- `git diff --check -- ui/roughcut/roughcut_major_panel.py tests/test_roughcut_ui_v2.py`
  - passed

### Live proof

- latest source app를 repo 기준 `./venv/bin/python main.py`로 다시 띄운 뒤 multicandidate Macau fixture를 열고 roughcut으로 진입했습니다.
- direct gesture:
  - B card 첫 row thumbnail click
  - 이어서 B card 둘째 row thumbnail click
- 최종 상태:
  - `selected_chapter_id = B_0015`
  - `selection_summary = 선택 B_0015 · 확정`
  - `video_position_ms = 64234`
  - 우측 플레이어 frame도 B row thumbnail click에 맞춰 갱신됐습니다.
- 즉 autoplay command proxy만이 아니라, 실제 thumbnail click 자체가 선택/preview 경로를 타는 것이 source app에서 확인됐습니다.

### Artifacts

- direct thumbnail click snapshot:
  - `output/manual_verification/latest/roughcut_thumbnail_click_direct_20260601.png`
- direct thumbnail click status:
  - `output/manual_verification/latest/roughcut_thumbnail_click_direct_20260601_status.json`

### Recommended next step

- direct thumbnail click, candidate click, chapter reorder, segment reorder, export가 모두 실앱에서 닫혔으므로 다음 우선순위는 polish입니다.
  - right player menu density 정리
  - card/meta 정보 우선순위 정리
  - roughcut full-page visual unification

## 2026-06-01 Addendum - Right Player Menu Density Cleanup

### Scope

- 우측 비디오 플레이어 아래 메뉴의 상태 뱃지 중복을 줄이고, 같은 정보를 더 짧은 요약 줄로 다시 묶었습니다.
- 기능/automation에 필요한 상태 텍스트는 유지하면서, 실제 화면에서는 `작업 / 내보내기 / 재생` 흐름이 먼저 읽히게 정리했습니다.

### Code change

- `ui/roughcut/roughcut_widget.py`
  - player menu 내부 `candidate/filter/order/selection/reorder` badge들은 내부 상태 holder로 유지하되 화면에서는 숨겼습니다.
  - 대신 visible summary block을 추가했습니다.
    - `player_context_summary_lbl`
    - `player_focus_summary_lbl`
    - `player_reorder_summary_visible_lbl`
  - button rows 앞에 `작업`, `내보내기`, `재생` section label을 추가했습니다.
  - `_refresh_player_runtime_summary()`를 추가해서 기존 setter들이 바꾸는 internal label text를 새 visible summary block에도 바로 반영하게 했습니다.
- `tests/test_roughcut_ui_v2.py`
  - `major_log_and_title_panels_render_without_removing_legacy_table`에서 새 player summary label 값을 같이 확인하게 보강했습니다.

### Validation

- `./venv/bin/python -m py_compile ui/roughcut/roughcut_widget.py tests/test_roughcut_ui_v2.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py -k 'major_log_and_title_panels_render_without_removing_legacy_table or ordered_preview_sequence_follows_visible_row_order or minor_card_reorder_updates_chapter_and_edl_order'`
  - `3 passed`
- `git diff --check -- ui/roughcut/roughcut_widget.py tests/test_roughcut_ui_v2.py`
  - passed

### Live proof

- latest source app를 repo 기준 `./venv/bin/python main.py`로 다시 띄우고 multicandidate Macau fixture를 열어 roughcut draft candidate로 진입했습니다.
- source app live 화면에서 player menu가 다음 구조로 바뀐 것을 확인했습니다.
  - candidate/filter -> 첫 summary line
  - order/selection -> 둘째 summary line
  - reorder -> 셋째 summary line
  - 그 아래 `작업 / 내보내기 / 재생` section label과 button rows
- live runtime 기준 roughcut state도 유지됐습니다.
  - `selected_candidate_id = editor_post_generation_roughcut_draft`
  - `selected_chapter_id = B_0014`
  - `filter_summary = 표시 45 / 전체 45`
  - `order_summary = 카드 2/4 · A > B > C > D`
  - `reorder_summary = 재정렬 없음`

### Artifacts

- compact player menu live snapshot:
  - `output/manual_verification/latest/roughcut_player_menu_compact_20260601.png`
- compact player menu live status:
  - `output/manual_verification/latest/roughcut_player_menu_compact_20260601_status.json`

### Recommended next step

- roughcut 기능 증빙은 이제 거의 닫혔고, 남은 우선순위는 full-page visual unification 쪽입니다.
  - left roughcut frame와 right player menu의 surface hierarchy 정리
  - bottom detail block density 정리
  - 마지막으로 save/reopen/reorder/thumbnail path를 한 번 더 release-style로 묶어 보기

## 2026-06-01 Addendum - Bottom Detail Density Cleanup

### Scope

- 하단 selected-chapter detail block을 더 짧은 읽기 흐름으로 다시 묶었습니다.
- 목적은 정보를 줄이는 게 아니라 `상단 요약 / 근거 / 수정 상태 / 컷 조정` 순서가 한 번에 읽히게 만드는 것이었습니다.

### Code change

- `ui/roughcut/roughcut_detail.py`
  - panel surface를 `#12191D / #243038` 계열로 정리해 right player menu와 더 비슷한 위계를 갖게 했습니다.
  - 기존 `챕터 / 사용 자막 / Story / 위험도 / 출력` 5칩 한 줄 구조를
    - `챕터 / 사용 자막 / 출력`
    - `Story / 위험도`
    2단으로 재배치했습니다.
  - `detail_reason_lbl`은 muted 9px + `maximumHeight(34)`로 좁혀서 근거 문장이 block을 과하게 밀지 않게 했습니다.
  - `수정 상태`와 `Δ In/Out`은 한 줄에서 같이 읽히게 다시 묶었습니다.
  - detail badges / input controls border radius와 background를 player menu 계열 톤으로 맞췄습니다.

### Validation

- `./venv/bin/python -m py_compile ui/roughcut/roughcut_detail.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py -k 'major_log_and_title_panels_render_without_removing_legacy_table or thumbnail_button_emits_preview_request_for_minor_row or minor_card_reorder_updates_chapter_and_edl_order'`
  - `3 passed`
- `git diff --check -- ui/roughcut/roughcut_detail.py`
  - passed

### Live proof

- latest source app를 repo 기준 `./venv/bin/python main.py`로 다시 띄우고 multicandidate Macau fixture에서 roughcut draft candidate로 진입한 뒤 current screen snapshot을 남겼습니다.
- runtime 상태는 유지됐습니다.
  - `selected_candidate_id = editor_post_generation_roughcut_draft`
  - `selected_chapter_id = B_0014`
  - `filter_summary = 표시 45 / 전체 45`
  - `order_summary = 카드 2/4 · A > B > C > D`

### Artifacts

- compact detail live snapshot:
  - `output/manual_verification/latest/roughcut_detail_compact_20260601.png`
- compact detail live status:
  - `output/manual_verification/latest/roughcut_detail_compact_20260601_status.json`

### Recommended next step

- remaining polish is now mostly top-level composition:
  - left candidate/major frame와 right video/menu frame의 vertical rhythm 정리
  - bottom tabs와 detail surface의 hierarchy 마지막 정리
  - 그 뒤 save/reopen/reorder/thumbnail path를 release-style로 한 번 더 묶어서 roughcut completion audit에 가까운 증빙 만들기

## 2026-06-01 Addendum - Release-Style Roughcut Audit Scenario

### Scope

- `tools/qa_suite_runner.py`에 roughcut full-flow completion audit를 위한 `roughcut_release_audit_macau` 시나리오를 추가했습니다.
- 목적은 이미 따로따로 증빙된 `candidate selection`, `thumbnail preview proxy`, `chapter reorder`, `save/reopen`, `roughcut export`, `snapshot` 경계를 하나의 release-style sequence로 다시 묶는 것이었습니다.

### Code change

- `tools/qa_suite_runner.py`
  - major profile에 `roughcut_release_audit_macau` app-sequence를 추가했습니다.
  - step flow:
    - `open_project`
    - `open_roughcut`
    - `status_ready`
    - `select_candidate_draft`
    - `thumbnail_preview_proxy`
    - `move_chapter_down`
    - `save_project`
    - `reopen_project`
    - `status_after_reopen`
    - `roughcut_export_srt`
    - `capture_release_audit`
  - multicandidate fixture는 이제 `_suite_fixtures`에 남아 있던 이전 reorder 상태를 재사용하지 않고, 매 build 시 fresh copy를 다시 써서 deterministic하게 만듭니다.
- `tests/test_qa_suite_runner.py`
  - major scenario 목록에 `roughcut_release_audit_macau`가 포함되는지 검증을 추가했습니다.
  - release-style roughcut audit step set과 export path를 별도 테스트로 묶었습니다.

### Validation

- `./venv/bin/python -m py_compile tools/qa_suite_runner.py tests/test_qa_suite_runner.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_qa_suite_runner.py -k 'release_style_roughcut_audit or core_macau_sequences'`
  - `2 passed`
- source app manual run:
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python - <<'PY' ... roughcut_release_audit_macau ... PY`
  - final result: `ok = true`

### Live proof

- release-style audit single scenario가 source app에서 끝까지 통과했습니다.
- 핵심 확인점:
  - `status_ready`에서 `current_work_mode = roughcut`, `candidate_count = 2`, `visible_row_count = 45`
  - `select_candidate_draft` 이후 `selected_candidate_id = editor_post_generation_roughcut_draft`
  - `thumbnail_preview_proxy` 이후 `selected_chapter_id = B_0015`, `selected_segment_id = B`
  - `move_chapter_down` 이후 `reorder_summary = 챕터 재정렬 · B_0016 > B_0015 > B_0017 > B_0018`
  - `status_after_reopen`에서도 `selected_candidate_id = editor_post_generation_roughcut_draft`, `candidate_count = 2`, `visible_row_count = 45`
  - export와 snapshot까지 same scenario output 안에서 생성됨

### Artifacts

- release audit summary:
  - `output/manual_verification/latest/qa_suite_release_audit_manual/roughcut_release_audit_macau/summary.json`
- release audit snapshot:
  - `output/manual_verification/latest/qa_suite_release_audit_manual/roughcut_release_audit_macau/snapshots/roughcut_release_audit.png`
- release audit export:
  - `output/manual_verification/latest/qa_suite_release_audit_manual/roughcut_release_audit_macau/exports/roughcut_release_audit_export.srt`

### Recommended next step

- roughcut completion audit는 이제 독립 시나리오로 닫혔고, 다음 우선순위는 visual polish와 gesture proof 정리입니다.
  - 후보 기둥 / major cards / right player menu의 full-page hierarchy 마지막 정리
  - thumbnail direct click / drag-and-drop direct gesture를 release-style artifact set 안에 한 번 더 포함할지 판단

## 2026-06-01 Addendum - Major Profile Green With Roughcut Audit

### Scope

- `roughcut_candidate_macau`와 `roughcut_release_audit_macau`를 포함한 최신 `major` source-app QA를 다시 돌려, roughcut 관련 시나리오가 전체 suite 안에서도 함께 녹색인지 확인했습니다.
- 이 과정에서 `roughcut_candidate_macau`의 candidate-state 기대값이 현재 문구 정책과 어긋나 있던 부분을 `저장된 자막 기준`으로 정리했습니다.

### Code change

- `tools/qa_suite_runner.py`
  - `roughcut_candidate_macau`의 `select_candidate_second`, `status_candidate_selected` 기대값을 현재 runtime 문구인 `저장된 자막 기준`으로 맞췄습니다.
- `tests/test_qa_suite_runner.py`
  - release-style roughcut audit 시나리오 목록/구성 보호 테스트는 그대로 유지했고, 최신 `tools/qa_suite_runner.py` 기준으로 다시 확인했습니다.

### Validation

- `./venv/bin/python -m py_compile tools/qa_suite_runner.py tests/test_qa_suite_runner.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_qa_suite_runner.py -k 'release_style_roughcut_audit or core_macau_sequences'`
  - `2 passed`
- candidate smoke 단독 source-app run:
  - `output/manual_verification/latest/qa_suite_candidate_manual/roughcut_candidate_macau/summary.json`
  - result: `ok = true`
- full source-app major profile:
  - `AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py major`
  - result: `ok = true`, `failed_count = 0`

### Live proof

- latest major suite root:
  - `output/manual_verification/latest/qa_suite_major_20260601_041624`
- roughcut scenarios inside the green suite:
  - `roughcut_candidate_macau/summary.json` -> `ok = true`
  - `roughcut_interaction_macau/summary.json` -> `ok = true`
  - `roughcut_release_audit_macau/summary.json` -> `ok = true`
  - `roughcut_reopen_macau/summary.json` -> `ok = true`
- suite result:
  - `suite_result.json`
  - `suite_result.md`

### Remaining risk

- roughcut 핵심 기능 경로는 major suite와 개별 live proof 기준으로 닫혔지만, visual polish는 여전히 선택 영역입니다. 이건 기능 미완료라기보다 presentation 정리 범주입니다.
- 후보/카드/우측 메뉴의 최종 미감 조정은 추가 작업 여지가 있지만, 현재 evidence 기준으로는 candidate 선택, thumbnail preview, reorder, save/reopen, sequence preview, export 흐름을 막는 기능 구멍은 보이지 않습니다.

### Recommended next step

- release/commit 전이라면 current roughcut state를 한번 더 사람이 눈으로 확인하고 저장합니다.
- 기능 목표 기준으로는 다음 큰 workstream으로 넘어갈 수 있고, 추가 작업을 한다면 visual polish를 별도 slice로 다루는 편이 안전합니다.

## 2026-06-01 Addendum - Roughcut Menu Grouping Pass

### Scope

- 러프컷 UI에서 우측 플레이어 아래 메뉴와 하단 패널이 평평하게 흩어져 보이던 부분을 `그룹` 중심으로 다시 묶었습니다.
- Antigravity `잼민이`와 메뉴 그룹핑 초안을 짧게 맞췄고, 실제 반영은 `Core Pipeline / Media Controller / Candidate+Filter / Export` 기준으로 좁게 적용했습니다.

### Jammini meeting outcome

- `Group 1 (Core Pipeline)`과 `Group 2 (Media Controller)`는 플레이어 바로 아래에 바로 노출
- `Group 3 (Data Filter & Candidate)`는 접을 수 있는 accordion
- `Group 4 (Export Deliverables)`는 개별 버튼 3개보다 단일 dropdown이 더 적절
- 추가 제안 중 `preview row` 완전 통합은 이번 슬라이스에서 보류하고, 우선 메뉴 그룹 경계만 먼저 강화

### Code change

- `ui/roughcut/roughcut_widget.py`
  - 우측 메뉴를 `핵심 작업 / 재생 컨트롤 / 후보·필터 / 내보내기` 4그룹으로 재구성
  - `SRT / EDL / 가이드` 3버튼을 `QToolButton` dropdown 하나로 묶음
  - `후보·필터`는 접을 수 있는 section으로 바꾸고 `safety_filter_combo`를 이 그룹 안으로 이동
  - 하단 control block은 `현재 상태`와 `선택 카드 편집` 2그룹으로 재분리
- `ui/roughcut/roughcut_bottom_panel.py`
  - 탭 구역을 `참조 패널`로 명시하고 설명 문구를 추가해, 하단 탭이 보조 참조 메뉴라는 위계를 분명히 함
- `tests/test_roughcut_ui_v2.py`
  - 새 그룹 제목과 export dropdown, `참조 패널` title을 확인하는 회귀를 추가

### Validation

- `./venv/bin/python -m py_compile ui/roughcut/roughcut_widget.py ui/roughcut/roughcut_bottom_panel.py tests/test_roughcut_ui_v2.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py -k 'major_log_and_title_panels_render_without_removing_legacy_table or candidate_preview_frames_limit_to_three_and_apply_selection or candidate_preview_toggle_applies_selection'`
  - `3 passed`
- `git diff --check -- ui/roughcut/roughcut_widget.py ui/roughcut/roughcut_bottom_panel.py tests/test_roughcut_ui_v2.py`
  - passed

### Visual proof

- updated offscreen mockup:
  - `output/manual_verification/latest/roughcut_menu_grouping_mockup_20260601.png`
- current grouping visible in the mockup:
  - right panel
    - `핵심 작업`
    - `재생 컨트롤`
    - `후보 / 필터`
    - `내보내기`
  - bottom area
    - `현재 상태`
    - `선택 카드 편집`
    - `참조 패널`

### Remaining risk

- 이번 슬라이스는 grouping 우선이라 `preview row` 자체의 버튼 밀도는 아직 남아 있습니다.
- source app를 재시작하지 않고 오프스크린으로 먼저 본 상태라, 실제 열린 앱에서 같은 위계가 바로 체감되는지는 다음 실앱 확인이 필요합니다.

### Recommended next step

- source app를 다시 띄울 타이밍이 되면 `roughcut_menu_grouping_mockup_20260601.png` 기준으로 실앱 snapshot을 한 번 더 남깁니다.
- 다음 visual polish를 더 한다면 `preview row`의 `반복 / 정지 / 구간 재생`을 더 짧은 media strip으로 합치는 쪽이 자연스럽습니다.

## 2026-06-01 Addendum - Proposal Top, Horizontal Cards Bottom

### Scope

- 러프컷 화면의 역할을 다시 분리했습니다.
- 위쪽 세로 후보 기둥은 `러프컷 제안 선택`만 맡고, 아래 메인 카드는 `선택한 제안의 카드 세그먼트 가로 표시`로 고정했습니다.

### Code change

- `ui/roughcut/roughcut_major_panel.py`
  - lower `major card` list를 세로 스택이 아니라 `LeftToRight` 가로 flow로 전환
  - major card drag surface/handle은 세로 delta가 아니라 가로 delta로 reorder를 해석
  - 선택 card는 더 넓게, 비선택 card는 더 좁게 유지해 하단에서 가로 카드 구성이 바로 읽히게 조정
  - 패널 설명 문구도 `위 제안 선택 -> 아래 가로 카드 정리` 기준으로 갱신
- `tests/test_roughcut_ui_v2.py`
  - `major_panel.card_list.flow() == LeftToRight` 회귀 추가
  - compact/expanded card budget을 가로 카드 기준으로 재검증

### Validation

- `./venv/bin/python -m py_compile ui/roughcut/roughcut_major_panel.py tests/test_roughcut_ui_v2.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py -k 'major_log_and_title_panels_render_without_removing_legacy_table or unselected_major_cards_stay_compact_while_selected_card_expands or five_major_cards_keep_compact_card_budget or selected_major_card_expands_to_show_multiple_minor_rows or drag_surfaces_emit_major_and_minor_reorder_requests'`
  - `5 passed`
- `git diff --check -- ui/roughcut/roughcut_major_panel.py tests/test_roughcut_ui_v2.py`
  - passed

### Visual proof

- updated offscreen mockup:
  - `output/manual_verification/latest/roughcut_top_proposals_bottom_horizontal_20260601.png`
- intended reading order:
  - top: `LLM 후보` 세로 기둥 선택
  - bottom: 선택한 후보의 `카드 세그먼트`를 가로 카드로 탐색

### Remaining risk

- 이번 슬라이스는 오프스크린 기준으로 먼저 닫았고, live source app 재시작 후 snapshot은 아직 남아 있습니다.
- major card native drag/drop는 가로 flow와 수동 drag delta 둘 다 맞춰뒀지만, 실앱에서 hit area 체감은 한 번 더 보는 편이 안전합니다.

## 2026-06-01 Addendum - Reduced Roughcut Menus

### Scope

- roughcut 우측/하단 메뉴가 겹치던 구성을 `상시 노출 최소화` 기준으로 다시 줄였습니다.
- 회의 결론대로 `후보 선택, 재생, 선택 카드 편집`만 전면에 두고, AI 작업과 내보내기, 보조 참조는 접거나 최소 탭만 남겼습니다.

### Code change

- `ui/roughcut/roughcut_widget.py`
  - 우측 제목을 `핵심 메뉴`로 정리
  - `AI 작업`을 기본 접힘 섹션으로 전환
  - `내보내기`를 기본 접힘 섹션으로 전환
  - 하단 `현재 상태`를 기본 접힘 섹션으로 전환
  - `가이드`, `제목`, `스타일` 패널은 계속 내부 상태/저장 경로에는 남기되 기본 탭 노출에서는 제외
- `ui/roughcut/roughcut_bottom_panel.py`
  - 섹션명을 `보조 참조`로 변경
  - 참조 탭을 `자막 세그먼트`, `EDL`만 남기고 축소
  - `글로벌 세그먼트`, `웨이브폼`, `스토리보드`는 기본 노출에서 제외
- `tests/test_roughcut_ui_v2.py`
  - 축소된 탭 개수와 이름
  - `AI 작업`, `내보내기`, `현재 상태`의 기본 접힘 상태
  - `핵심 메뉴` 제목을 회귀로 고정

### Validation

- `./venv/bin/python -m py_compile ui/roughcut/roughcut_widget.py ui/roughcut/roughcut_bottom_panel.py tests/test_roughcut_ui_v2.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py -k 'major_log_and_title_panels_render_without_removing_legacy_table or candidate_preview_frames_limit_to_three_and_apply_selection or candidate_preview_toggle_applies_selection or drag_handles_exist_for_major_and_minor_cards'`
  - `4 passed`
- `git diff --check -- ui/roughcut/roughcut_widget.py ui/roughcut/roughcut_bottom_panel.py tests/test_roughcut_ui_v2.py`
  - passed

### Visual proof

- updated offscreen mockup:
  - `output/manual_verification/latest/roughcut_menu_reduced_mockup_20260601.png`

### Remaining risk

- 이번 턴은 오프스크린 mockup 기준입니다. live source app 재시작 후 같은 축소 구성이 실제 러프컷 화면에서도 과하게 숨겨지지 않는지 한 번 더 보는 편이 안전합니다.

## 2026-06-01 Addendum - Candidate Origin And LLM-Only Filter

### Scope

- roughcut 후보가 `실제 LLM 초안`, `로컬 초안`, `임시 placeholder` 중 무엇인지 화면에서 바로 구분되게 했습니다.
- `LLM 결과만` 필터를 후보 영역에 추가해, 실제 LLM으로 생성된 roughcut 초안만 따로 볼 수 있게 했습니다.

### Code change

- `ui/roughcut/roughcut_state.py`
  - candidate payload에 `candidate_origin`을 저장
  - `warnings`, `draft_state`, `schema_version`, `candidate_id` 기준으로 `llm / local / placeholder`를 판정
- `ui/roughcut/roughcut_widget.py`
  - 후보 영역 상단에 `전체 후보 / LLM 결과만` 필터 추가
  - 후보 기둥 header와 접근성 텍스트에 `실제 LLM / 로컬 초안 / 임시 상태` origin 배지 노출
- `tests/test_roughcut_ui_v2.py`
  - origin 배지와 `LLM 결과만` 필터 회귀 추가

### Validation

- `./venv/bin/python -m py_compile ui/roughcut/roughcut_widget.py ui/roughcut/roughcut_state.py tests/test_roughcut_ui_v2.py`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_roughcut_ui_v2.py -k 'candidate_state_and_filter_badges_follow_selection or candidate_preview_frames_limit_to_three_and_apply_selection or candidate_preview_toggle_applies_selection or candidate_preview_filter_shows_only_llm_candidates or major_log_and_title_panels_render_without_removing_legacy_table'`
  - `5 passed`
- `git diff --check -- ui/roughcut/roughcut_widget.py ui/roughcut/roughcut_state.py tests/test_roughcut_ui_v2.py`
  - passed
