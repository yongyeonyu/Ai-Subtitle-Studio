<!--
Document-Version: 04.00.11-mac-native
Phase: MAC_NATIVE_APPSTORE_V4_0_11_RELEASED
Last-Updated: 2026-05-20
Updated-By: Codex
Purpose: Remaining work queue only.
-->
# ACTION_ITEMS.md - Remaining Work Queue

## Queue Policy

- This file contains only unfinished or parked work.
- Completed items are removed instead of kept as history.
- Release history belongs in `RELEASE_v*.md`.
- Bootstrap and operating rules belong in `AGENTS.md`.
- Native migration details belong in `NATIVE_LIB_PLAN.md`.
- Countable action items are the checked/unchecked rows under **Active Work** only.

## Metadata

```yaml
app_version: "04.00.11"
document_version: "04.00.11-mac-native"
phase: "MAC_NATIVE_APPSTORE_V4_0_11_RELEASED"
next_phase: null
active_item_count: 15
commit_policy: "Commit only when the user explicitly asks."
product_priority: "Accuracy before speed; optimize generation time only with behavior-preserving changes."
native_plan: "NATIVE_LIB_PLAN.md"
```

## Action Execution Rules

- Treat optimization and performance improvement as the top priority for action-item execution and implementation choice, as long as subtitle quality, verified behavior, and required user workflows do not regress.
- Refactor code when it can be done inside the approved scope without changing behavior.
- After modifying code, perform a code-review pass, fix the review findings, and only then report completion.
- Prefer implementations that improve launch/runtime speed or reduce memory, CPU, disk, or bridge overhead.
- Do not change existing UI, UX, or behavior as part of generic action-item work. If a change appears necessary, leave it as an owner-decision item and ask for approval first.
- When a function-level path can be equal or faster with `.cpp`, `.swift`, `.js`, or another native/runtime language, implement that path with parity tests and a safe Python fallback.
- Store UX-related behavior in separate files under an appropriate `ux/` folder whenever possible so UX scenarios are not accidentally deleted from owner widgets.
- Use real fixtures for action-item verification when execution is required:
  - Macau fixture: `/Users/u_mo_c/Downloads/마카오테스트` for quick UI, UX, playback, restart, and generation smoke checks.
  - Tinyping fixture: `/Users/u_mo_c/Downloads/티니핑/티니핑_유스어드벤처.MP4` for long generation, roughcut, ETA, queue, memory, and full-flow checks.
  - Test-video fixture: `/Users/u_mo_c/Downloads/ai_subtitle_studio/test video` for benchmark and regression checks.
  - X5 subtitle fixture: `test video/X5_시승기_후반.MP4` plus its sibling `.srt` for subtitle-accuracy verification slices.
- If the owner asks "how many action items are left?", answer with the number of countable active items that can be executed sequentially in one pass.
- If the owner says "run N items" or "do 5 items", execute the first N unchecked active items in order unless a blocker or owner-decision item is reached.

## Active Work

### P3 - UX Automation Coverage (Automation-4)

- [x] 23. 멀티클립 파이프라인 시나리오의 앱 타임아웃/대기 상태 해소
  범위: `queue-files` → 메인 윈도우 준비 타임아웃/`app_unreachable` 상태에서 단계별 타임아웃 원인 분리.
  성공 기준: 3개 이상 멀티클립 입력 시 `queue row`가 `all_done`으로 수렴하고 `status_snapshot_fallback` 없이 완료 상태 확인.
  Progress: 2026-05-20 `tools/automation_command_client.py`로 `status/ping/guided-subtitle-status` 준비 대기 재시도를 추가해 앱 시작 직후 `queued_until_main_window_ready`와 일시 `app_unreachable`를 분리했다.
  Progress: 2026-05-20 집중 재실행에서 `start-multiclip` CLI는 `app_unreachable/timed out`로 실패했지만, 앱 로그는 `전체 5/5개 클립 처리 완료`까지 진행됐다. 현재 문제는 기능 자체보다 멀티클립 중 status/ack 관측 불안정에 가깝다.
  Progress: 2026-05-20 `start-multiclip`에서 editor wait/auto-start 동기 대기를 제거하고 즉시 `accepted=true`, `queued=true` 응답으로 변경했다.
  Progress: 2026-05-20 마카오 5클립 재실행에서 `start-multiclip` 응답이 즉시 성공했고, `status` 2회차에 `row_count=5`, `done_rows=5`, `all_done=true`, `status_snapshot_fallback` 없이 수렴했다.
  검증: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/multiclip_fast/*`, `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_120128_automation4_action_items_rerun/command_status.tsv`, `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_131332_automation4_multiclip_ack_macau/command_status.tsv`

- [x] 24. 세그먼트 편집 시퀀스(선택/분할/인라인 편집/이동/병합) 실패 구간 원인 분리
  범위: `editor_project_sequence` 단계별 실패 원인(큐지연, 선택되지 않음, 명령 미지원) 재현 경로 분해.
  성공 기준: 1개도 `ok=False` 단계 없이 full-editor 시나리오 1pass 완료.
  Progress: 2026-05-20 마카오 프로젝트에서 `open-project -> set-playhead -> snapshot` command-only smoke는 통과했다. snapshot-each-step은 캡처 파일 큐 특성 때문에 별도 안정화가 필요하다.
  Progress: 2026-05-20 `remote_verify --actions`에 `play`, `pause`, `save-project`를 추가하고 마카오 프로젝트에서 한 시나리오로 증거화했다.
  Progress: 2026-05-20 집중 재실행 direct command 기준 `set-playhead`, `select-segment`, `move-segment-left/right`, `move-diamond`, `merge-diamond`는 통과했고 실패는 `begin-smart-split=smart_split_unavailable`, `set-inline-cursor/commit-inline-edit=inline_edit_inactive`로 좁혀졌다.
  Progress: 2026-05-20 `editor-begin-smart-split`를 playhead segment fallback으로 보강하고, 마카오 targeted function test에서 `set-playhead -> begin-smart-split(line 0) -> set-inline-cursor -> commit-inline-edit`가 모두 `ok=true`로 통과했다.
  Progress: 2026-05-20 full-editor 1pass 재실행에서 `open-project` 직후 settle 없이 바로 `begin-smart-split`를 넣으면 playhead가 다시 `0.0`으로 덮이며 실패하는 패턴을 확인했다.
  Progress: 2026-05-20 `open-project` 후 2초, `set-playhead` 후 1초 settle을 두고 compact action path(`begin-smart-split --at-playhead -> set-inline-cursor -> commit-inline-edit -> move-segment-left/right -> move-diamond -> merge-diamond`)로 재실행한 결과 모든 단계가 `ok=true`로 통과했다.
  Progress: 2026-05-20 `remote_verify` full-editor report에서도 `open -> set-playhead -> select -> begin-smart-split -> set-inline-cursor -> commit-inline-edit -> move-segment-left/right -> move-diamond -> merge-diamond -> snapshot` 전 단계가 `ok=true`로 재확인됐다.
  검증: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/editor_project_sequence/*`, `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_120128_automation4_action_items_rerun/command_status_direct.tsv`, `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_125219_automation4_item12_macau_function_retry/command_status.tsv`, `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_161630_automation4_editor_fullpass_macau_compact/command_status.tsv`, `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_automation4_editor_fullpass_macau/report.json`

- [x] 25. 재생 제어 커맨드 안정화 (play/pause + 비디오 메뉴)
  범위: `playback_play`, `playback_pause`, video 메뉴 전환 커맨드의 타임아웃/리트라이 정책.
  성공 기준: 재생 시작/정지 상태가 앱 응답 후 status에서 일관되게 관측.
  Progress: 2026-05-20 마카오 프로젝트에서 `editor-playback play`와 `editor-playback pause`가 모두 `ok=true`로 응답했고 status에서 editor_runtime을 확인했다.
  Progress: 2026-05-20 `remote_verify --actions play pause`로 같은 report 안에서 play/pause 증거를 남길 수 있게 했다.
  Progress: 2026-05-20 집중 재실행 fresh app에서도 `editor-playback play/pause`가 각각 `ok=true`로 재확인됐다.
  Progress: 2026-05-20 `editor-video show/hide/toggle` command surface를 추가했고, 마카오 project run에서 `video_visible=false -> true` 전환과 snapshot 저장까지 확인했다.
  검증: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/playback_play.json`, `playback_pause.json`, `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_120128_automation4_action_items_rerun/command_status_direct.tsv`, `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_133752_automation4_video_menu_macau/command_status.tsv`

- [x] 26. 프로젝트 저장/자막 저장/내보내기 경로를 테스트 케이스로 확정
  범위: `save-project` 취소가 아닌 성공 저장, 자막 저장 파일 경로 검증, 자막 출력/영상 출력 산출물 확인.
  성공 기준: 저장 후 프로젝트·자막·출력파일 존재 확인 및 경로/크기/라인 수 회귀 체크.
  Progress: 2026-05-20 마카오 프로젝트에서 `remote_verify --actions save-project`가 `project_saved`로 성공했다.
  Progress: 2026-05-20 집중 재실행 direct command에서도 `save-project`가 `ok=true`로 재확인됐고 저장 직후 editor snapshot을 남겼다.
  Progress: 2026-05-20 `save-subtitles`, `export-subtitles`, `export-subtitle-video` command surface를 추가했다.
  Progress: 2026-05-20 첫 저장/출력 재실행에서는 stale app process 때문에 `unknown_command`가 발생했고, 앱 재기동 후 `변경사항이 없습니다` 경로에서도 기존 SRT를 역추론하도록 fallback을 보강했다.
  Progress: 2026-05-20 마카오 retry에서 `save-project`, `save-subtitles`, `export-subtitles`, `export-subtitle-video`가 모두 `ok=true`로 통과했고 project/SRT/MOV 파일 존재·bytes·mtime을 확인했다.
  검증: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/save_project_before_roughcut.json`, `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_120128_automation4_action_items_rerun/command_status_direct.tsv`, `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_134922_automation4_save_export_macau_retry/command_status.tsv`, `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_134922_automation4_save_export_macau_retry/summary.json`

- [x] 27. 메뉴/LoRA/화자/STT 메뉴 커버리지 자동화 추가
  범위: UI 메뉴 트리 순회(설정/사전/딕셔너리/화자/LoRA start-stop), STT 모드 토글 커맨드 연동.
  성공 기준: 각 메뉴 1회 호출 시 `snapshot` 또는 상태 응답이 정상 기록되고 실패 항목이 누적되지 않음.
  Progress: 2026-05-20 `app_command_bridge`/`appctl`에 `open-settings`, `open-speaker-settings`, `capture-active-dialog`, `close-active-dialog`, `editor-stt-mode`, `personalization-idle`를 추가했다.
  Progress: 2026-05-20 집중 재실행에서 settings/speaker/dictionary popup 캡처와 STT on/off status는 모두 통과했다.
  Progress: 2026-05-20 `personalization-idle run-now`는 CLI 기준 타임아웃이었지만 앱 로그상 `LoRA 학습 시작`이 실제로 발생했다. `pause/resume`는 여전히 타임아웃이다.
  Progress: 2026-05-20 `personalization-idle run-now/pause/resume`를 async `accepted + queued` 응답으로 보강했고, 마카오 targeted function test에서 3개 명령이 모두 `ok=true`로 통과했다.
  Progress: 2026-05-20 `remote_verify --actions`에 menu/dialog/STT/LoRA alias를 추가했고, 마카오 project full pass에서 dictionary/settings/speaker popup PNG, STT on/off status, `lora-run-now/pause/resume` ack를 한 report로 재확인했다.
  검증: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_automation4_menu_stt_lora_macau/report.json`, `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_automation4_menu_stt_lora_macau/capture-dictionary.png`, `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_automation4_menu_stt_lora_macau/capture-active-dialog.png`, `test_case.md`

### P2 - Help Manual And QA Mapping

- [ ] 28. 초보자용 도움말 재구성 + 도움말 장별 QA 자동화 매핑 구축
  범위: UI/UX 홈 동작, 프로젝트/미디어/SRT 열기, 자막 생성, 러프컷, 비디오/캔버스/타임라인, 자막 세그먼트 편집, 메뉴/팝업, 저장/출력, 화자/STT/LoRA 흐름의 owner 파일/핵심 함수와 현재 `qa_suite_runner` 커버리지를 매트릭스로 정리하고, 이를 기준으로 도움말과 QA 시나리오를 다시 설계한다.
  성공 기준: 초보자 기준의 새 도움말이 `기초 사용 -> 편집/캔버스 -> 메뉴/고급 기능 -> 저장/출력 -> 문제 확인` 순서로 재구성되고, 각 도움말 항목마다 `빠른검증/주요검증/전체검증` 중 어느 profile이 책임지는지와 실제 스냅샷/산출물 경로가 연결된다.
  Next: 1) `ui/home_ui.py`, `ui/home_sidebar.py`, `ui/editor/editor_widget.py`, `ui/editor/ux/editor_timeline_video.py`, `ui/editor/ux/timeline_input.py`, `ui/editor/ux/timeline_subtitle_segment_editing.py`, `ui/timeline/timeline_widget.py`, `ui/timeline/timeline_canvas.py`, `ui/settings/settings_dictionary.py`, `ui/main/app_command_bridge.py`, `tools/appctl.py`, `tools/qa_suite_runner.py` 기준으로 기능 owner와 자동화 커버리지 매트릭스를 작성한다.
  Next: 2) 현재 자동화에 없는 `show-home`, `open-srt`, `open-media`, `start-current-pipeline`, `start-current-roughcut`, `start-multiclip`, `queue-folder`, `queue-files`, `editor-pin-shadow-playhead`, `editor-clear-shadow-playhead`, `editor-zoom-max`, `editor-select-segment` 등의 누락 경로를 새 help chapter 기준으로 분류하고 runner 확장 대상을 결정한다.
  Next: 3) 새 도움말은 기존 문서를 참고만 하고 처음부터 다시 작성하며, 각 장마다 실제 앱 스냅샷 PNG와 관련 QA scenario id, fixture, 기대 결과를 함께 적는다.
  Next: 4) 도움말 장 구조를 그대로 `quick/major/full` 실행 프로파일과 연결해, 이후 사용자가 특정 장 또는 profile을 요청하면 앱을 실제 구동해 해당 범위만 검증하고 결과를 바로 보고할 수 있게 한다.
  검증: 도움말 초안 + 기능/함수/QA coverage matrix + `quick/major/full` profile별 chapter mapping + 실제 스냅샷 artifact 세트.

### P0 - UX And Editor Refactor Boundaries

- [ ] 7. Create an explicit editor session model for subtitle/STT/preview lanes.
  Scope: canonical segment store, selected STT evidence, final subtitle rows, preview rows, voice activity, and project-save views.
  Success: editor, timeline, video overlay, and save pipeline consume lightweight views of one canonical session model.
  Verification: project-open Tinyping `.aissproj` plus unit tests for save/reload.

### P0 - Architecture And Runtime Reliability

- [ ] 8. Create a project session service for open/save/reopen/resume flows.
  Scope: move lifecycle ownership out of UI panels and large project-manager branches.
  Success: project create/open/save/reopen/linked-SRT flows use one session service and dedicated serialization helpers.
  Verification: project-open/save/reopen tests plus Macau project smoke.

- [ ] 9. Replace direct queue widget mutation with a queue state model.
  Scope: queue table, sidebar queue panel, top card, elapsed/ETA/progress, completion state, and backend queue emits.
  Success: producers emit state updates and stop touching `QTableWidget` internals.
  Verification: queue/sidebar tests and Macau smoke.

- [ ] 10. Continue exception hygiene and structured logging burn-down.
  Scope: replace broad silent catches in high-risk UI/runtime/audio/project/cut-boundary paths with typed nonfatal logging.
  Success: no new broad silent exception patterns in touched files; real failures are visible in terminal or app logs.
  Progress: 2026-05-20 `ui/main/app_command_bridge.py`의 command 분기군을 handler module로 분리해 maintenance guard를 통과시켰고, bridge nonfatal/status helper는 기존 표면을 유지한 채 좁혔다.
  Progress: 2026-05-20 `core/pipeline/subtitle_memory_guard.py`에서 generation memory guard의 stage emit/checkpoint 준비 실패를 typed nonfatal log로 노출해, 반복 벤치 중 memory guard 예외가 조용히 사라지지 않게 했다.
  Progress: 2026-05-20 `ui/main/main_runtime_cleanup.py`의 post-generation GC가 `_post_generation_models_release_requested`가 남아 있으면 강제 모델 해제를 한 번 더 재시도하게 해, 첫 async release 요청이 놓쳐져도 warm-session 정리 요청이 드롭되지 않게 했다.
  Progress: 2026-05-20 마카오 반복 실앱에서는 run 자체보다 `guided-subtitle-status`/`ping`가 `app_unreachable`로 빠지는 구간이 더 직접적인 자동화 병목으로 확인됐다. main-thread 로그상 run 2는 끝까지 완료됐으므로 다음 패스는 busy editor/save/export 동안 command server 응답성을 좁혀야 한다.
  Verification: maintenance guard plus targeted tests for touched files.

- [x] 11. Debug and split the maintenance-budget file-length failure in `ui/main/app_command_bridge.py`.
  Scope: isolate status snapshot, dialog/menu automation, editor automation commands, and save/export command families so `app_command_bridge.py` drops below the maintenance file-length limit without changing automation behavior.
  Success: `./venv/bin/python tools/check_maintenance_budget.py --json` reports no `file_length` issue for `ui/main/app_command_bridge.py` in the touched scope.
  Progress: 2026-05-20 `ui/main/app_command_bridge_handlers.py`로 editor/snapshot/open/save/personalization/pipeline command family를 분리했고, `app_command_bridge.py`는 955 lines로 줄였다.
  Progress: 2026-05-20 `tools/check_maintenance_budget.py --json`가 changed scope 기준 `issue_count=0`으로 통과했고, 마카오 editor/menu smoke도 재통과했다.
  Verification: `tests.test_app_command_bridge`, `tests.test_remote_verify_actions`, `tests.test_automation_command_client`, `tools/check_maintenance_budget.py --json`, `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_maintenance_guard_split_macau_editor/report.json`, `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_maintenance_guard_split_macau_menu/report.json`

- [ ] 12. Stabilize app-command responsiveness while guided subtitle generation and save/export are busy.
  Scope: `core/automation/app_command_server.py`, `ui/main/app_command_bridge.py`, status snapshot fallback, main-thread command dispatch, and busy-stage automation polling during `guided-subtitle-run`.
  Trigger: real Macau repeat runs complete in the main log, but `guided-subtitle-status` and `ping` still fall into `app_unreachable` during processing or right after `save_export_*`.
  Success: `tools/debug_guided_subtitle_memory.py` and `tools/appctl.py` can observe `guided-subtitle-status`/`ping` through Macau repeat runs without repeated timeout collapse, and completion can be verified from live command responses instead of snapshot-only fallback.
  Progress: 2026-05-20 `core/automation/app_command_server.py`를 read-only command 병렬 처리 + stateful command 직렬 처리로 바꿔, `guided-subtitle-run` 같은 느린 명령이 UDP recv loop 전체를 막지 않게 했다.
  Progress: 2026-05-20 `ui/main/app_command_bridge.py`의 busy status fast-path가 `ST_PROC`/`backend_active`/`active_labels`를 보면 Qt signal을 건너뛰고 fallback snapshot을 cache까지 저장하도록 보강했다.
  Progress: 2026-05-20 stale cache를 무기한 재사용하면 run 1의 `ST_PROC` 상태가 run 2 idle 관찰까지 끌려오는 역효과가 확인돼, busy stale reuse는 `2.5s` 상한으로 다시 좁혔다. `guided-subtitle-run` 시작 응답은 status cache를 즉시 prime하도록 유지했다.
  Progress: 2026-05-20 targeted tests `tests.test_app_command_server`, `tests.test_app_command_bridge`, `tests.test_automation_command_client` 58개는 통과했고, busy fallback/worker-serialization 회귀를 추가했다.
  Progress: 2026-05-20 마카오 실앱 repeat2 재검증 (`output/manual_verification/latest/20260520_action_batch_app_command_responsiveness_macau_repeat2_v2`)에서는 run 1 `23.239s`, run 2 `72.394s`로 둘 다 `completed_via_snapshot=true`, `critical_reuse_stop_runs=0`, `runtime/memory pressure=normal`까지는 확인됐다.
  Progress: 2026-05-20 다만 같은 repeat2 run 2에서도 `guided_status_history.jsonl`의 `wait_pre_run_idle`, `wait_processing_start`, `wait_processing_done`에 timeout이 남았고, `ping_history.jsonl`에도 `app_unreachable`가 반복됐다. 즉, recv-loop starvation은 줄였지만 busy save/export 이후 status/ping 응답 collapse는 아직 남아 있다.
  Progress: 2026-05-20 stale reuse 상한 재조정 후 fresh app 마카오 repeat1 smoke (`output/manual_verification/latest/20260520_action_batch_app_command_responsiveness_macau_repeat1_v4`)는 `elapsed_sec=13.349`, `critical_reuse_stop_runs=0`, `runtime/memory pressure=normal`로 끝났고, 오래된 `ST_PROC` snapshot이 다음 run까지 끌려가는 회귀는 제거했다. 다만 `ping_history.jsonl`에는 여전히 `app_unreachable` 1건이 남았다.
  Verification: repeated Macau `guided-subtitle-run` 3x with `guided_status_history.jsonl`, plus targeted app-command tests for busy status fallback and post-save/export responsiveness.

- [x] 13. Land one-command QA runner as the official automation entrypoint.
  Scope: `tools/qa_suite_runner.py`, `tests/test_qa_suite_runner.py`, current-code app launcher, app-sequence isolation, fixture-adaptive editor actions, suite manifest/result output, and full-media summary parsing.
  Success: one command can run `quick`, `major`, and `full`; all three profiles pass on real fixtures with saved suite artifacts.
  Progress: 2026-05-20 stale `dist/macos` bundle을 최신 workspace 코드 기준으로 재생성했고, runner bootstrap을 해당 bundle 우선으로 통일했다.
  Progress: 2026-05-20 `editor_compact_macau`는 동적 playhead 선택과 `diamond_* boundary_sec` 기반 command 조립으로 fixture drift를 흡수하도록 보강했다.
  Progress: 2026-05-20 `full_media` stdout parse는 마지막 JSON line fallback을 읽도록 보강해 Tinyping 60초 `fast/auto/high` 3개가 suite summary에 그대로 반영되게 했다.
  Verification: `output/manual_verification/latest/qa_suite_quick_20260520_174600`, `output/manual_verification/latest/qa_suite_major_20260520_183244`, `output/manual_verification/latest/qa_suite_full_20260520_193515`, latest bundle-refreshed `output/manual_verification/latest/qa_suite_full_20260520_210149`

- [ ] 14. Split audio processing into durable services.
  Scope: extraction, chunking, transcription, VAD, cache decisions, worker pooling, retry policy, and resource cleanup.
  Success: common subprocess/worker cleanup policy is shared and persistent worker ownership is explicit; memory-pressure worker reuse decisions stay test-covered.
  Next: keep the current accepted `candidate1` cleanup policy, then inspect stage-level trim cost and STT/LLM worker residency before loosening more cleanup calls.
  Verification: audio/STT tests plus X5 or Tinyping slice when subtitle accuracy can be affected.

### P1 - Performance, Memory, And Tooling

- [ ] 15. Reduce duplicated segment/project state and lazy-hydrate large assets.
  Scope: editor/timeline/STT/save payload duplication, candidate lattices, preview rows, quality payloads, and large text assets.
  Success: project open/save and subtitle generation do not eagerly copy or retain large optional tracks until a lane/panel needs them.
  Next: use `output/runtime_monitor/latest.json` and `output/memory_monitor/subtitle_generation_latest.json` to confirm whether repeated generation still reaches `critical` after STT worker cleanup.
  Verification: project load/save tests plus memory snapshot on Tinyping when relevant.

- [ ] 16. Debug why repeated generation still reaches `critical` and disables STT persistent worker reuse.
  Scope: repeated Macau/X5/Tinyping generation, `output/runtime_monitor/latest.json`, `output/memory_monitor/subtitle_generation_latest.json`, `stage_trim_summary`, persistent WhisperKit/MLX/Ollama worker residency, and macOS compressed/swap growth.
  Trigger: runtime logs still report `메모리 critical: STT persistent worker 재사용 중단` during real runs.
  Success: identify the exact stage/family that pushes memory into `critical`, quantify whether the main cause is worker residency, cache retention, trim latency, or project/state duplication, and document the next behavior-preserving fix target.
  Next: compare cold-start vs repeated-run Macau/X5 slices, capture `process_snapshot_after` + `stage_trim_*` metrics per run, and verify whether worker shutdown happens before or after `stt_transcribe_chunk`, `subtitle_optimize_done`, or `save_export_done`.
  Progress: 2026-05-20 `tools/debug_guided_subtitle_memory.py`를 추가해 실앱 `guided-subtitle-run` 반복 중 `guided-subtitle-status`, runtime/memory monitor, guided snapshot PNG, 잔류 WhisperKit/MLX/Ollama 프로세스를 함께 저장하도록 했다. status timeout이 나도 `completed` snapshot으로 완료를 판정한다.
  Progress: 2026-05-20 마카오 실앱 warm session에서는 `guided-subtitle-status` live snapshot에서 `runtime_resource.pressure_stage=critical`이 재현됐고, recent stage logs에 `🧹 [STT2] 메모리 critical: STT persistent worker 재사용 중단`, `🧹 [STT1] 메모리 critical: STT persistent worker 재사용 중단`가 함께 보였다.
  Progress: 2026-05-20 fresh app 마카오 1회 검증에서는 `critical`이 재현되지 않았지만, 종료 직후에도 `Ollama`, `ollama`, `WhisperKitPersistentWorker`, `Python` 4개 프로세스가 남아 있었고 RSS는 `889126912 -> 87113728 bytes`로 크게 줄었다. 즉, residency는 유지되지만 메모리 해제량은 큰 편이라 다음 패스는 `critical` 자체를 만드는 warm-session 조건과 compressed memory 증가를 더 직접 좁혀야 한다.
  Progress: 2026-05-20 `20260520_action_batch_post_generation_release_retry_macau_repeat3_rerun/run_01/guided_memory_debug.json`에서는 `critical` reuse-stop 로그 없이 `warning`으로만 끝났고, `process_rss_after_settle_bytes`가 약 `0.087GB`까지 내려갔다. 이번 배치의 release retry는 최소한 첫 반복 run의 warm-session 잔류를 `critical`까지 밀어 올리지는 않았다.
  Progress: 2026-05-20 다만 같은 반복 검증의 run 2부터는 앱 명령 서버가 `app_unreachable` timeout으로 흔들렸고, 앱 메인 로그에는 실제 파이프라인 완료가 남았다. 현재 남은 병목은 STT worker reuse stop 자체보다 busy 상태의 command/status 응답면과 save/export 이후 idle 복귀 타이밍이다.
  Verification: repeated Macau fast benchmark plus X5 or Tinyping slice with memory artifacts saved under `output/manual_verification/latest/`.

- [ ] 17. Add dead-code and stale-QML-binding review.
  Scope: high-confidence unused Python functions, stale QML property bindings, duplicate native cut-boundary paths, and dynamic Qt signal wiring.
  Success: removable dead code is deleted only after static and dynamic wiring checks.
  Verification: targeted symbol scan plus QML/offscreen smoke where applicable.

- [ ] 18. Stage별 trim 비용을 계측해서 다음 반복 최적화 후보를 좁힌다.
  Scope: `core/runtime/memory_manager.py`, `core/pipeline/single_pipeline.py`, `output/runtime_monitor/latest.json`, `output/memory_monitor/subtitle_generation_latest.json`
  Assumption: 현재는 cleanup 완화 자체보다 `어느 stage trim이 실제 느린지`가 더 중요한 병목 정보다.
  Next: use `stage_trim.elapsed_ms`, `stage_trim.action_timings`, and `stage_trim.failures` from subtitle-generation snapshots to decide whether native/runtime cleanup calls are the next bottleneck.
  Progress: 2026-05-20 `core/runtime/memory_trim_summary.py`를 추가해 `subtitle_generation_latest.json`에 stage family별 trim 누적 횟수/elapsed/failure/action rollup을 남기고, `tools/verify_full_media_pipeline.py`가 해당 수치를 `summary_metrics`/`repeat_summary.csv`로 내보내도록 했다.
  Progress: 2026-05-20 마카오 fast repeat 3회에서 `pressure_stage=normal`로 trim 자체는 실행되지 않았고 `stage_trim_*` 수치는 비어 있었다. 다음 패스는 이 계측을 실제 `single_pipeline` 경로 또는 pressure 재현 run에 연결해 숫자를 채워야 한다.
  Progress: 2026-05-20 실앱 마카오 run artifact `20260520_action_batch_guided_memory_macau_repeat3_v3/run_01/subtitle_generation_monitor_after.json`에서 `subtitle_generation_stage=stt_optimizer_threads_done`, `stage_trim_executed_count=1`, `stage_trim_total_elapsed_ms=14.669`가 확인됐다.
  Success: `cut_prescan_done`, `subtitle_optimize_done`, `stt_optimizer_threads_done`, `save_export_done` 주변의 trim 횟수와 비용을
  마카오/X5 반복 벤치에 연결해서 다음 후보를 숫자로 선택할 수 있을 것.
  Verification: 마카오/X5 10회 반복 + stage별 trim 로그 비교.

### P1 - Native Library Queue

- [ ] 19. Benchmark native media-info normalization against the current cached Python path.
  Scope: only probe-result normalization and cache-key shaping, not full ffprobe orchestration.
  Success: native path is kept only if it is equal or faster on real project open/save benchmarks.
  Details: see `NATIVE_LIB_PLAN.md`.

- [ ] 20. Prepare cut-boundary scoring/alignment loops for native migration.
  Scope: isolate deterministic numeric loops after the cut-boundary Python refactor lands.
  Success: Swift/C++ path has parity tests and Python fallback before becoming default.
  Details: see `NATIVE_LIB_PLAN.md`.

- [ ] 21. Prepare subtitle candidate scoring and sequence smoothing for native migration.
  Scope: STT candidate scoring, lattice overlap scoring, subtitle timing, and word resegmenting hot loops.
  Success: native path improves or matches accuracy/speed and does not change final subtitle quality.
  Verification: X5 accuracy slice.

- [ ] 22. Split oversized Swift core files before adding more native features.
  Scope: `TimelineEditing.swift`, `NativePolicyEngine.swift`, and `RuntimeETAEstimator.swift`.
  Progress: 2026-05-20 `TimelineEditing.swift`를 contract/models, drag/geometry, magnet, preview/STT selection, persistence/serialization 파일로 분리해 단일 1815-line 파일을 `TimelineEditingModels.swift` 478 lines, `TimelineEditingDrag.swift` 451 lines, `TimelineEditingPreviewSelection.swift` 441 lines, `TimelineEditingPersistence.swift` 248 lines, `TimelineEditingMagnet.swift` 209 lines로 낮췄다.
  Progress: 2026-05-20 `RuntimeETAEstimator.swift`를 public API, models, prediction, request parsing, store persistence 파일로 분리해 단일 709-line 파일을 `RuntimeETAEstimator.swift` 67 lines + helper files로 낮췄고 `swift test` 38개가 통과했다.
  Progress: 2026-05-20 current-code bundle rebuild 뒤 `tools/qa_suite_runner.py quick`가 pass했고, 마카오 직접 파이프라인 검증 `output/manual_verification/latest/20260520_native_swift_split_macau_high_verify`에서 `mode=high`, `final_segment_count=48`, `completion_avg_quality=71.008`로 완료됐다.
  Next: `NativePolicyEngine.swift`를 scoring/retrieval/decision 책임으로 같은 방식으로 분리하고, 이후 필요 시 bridge payload 계측(item 5)과 연결한다.
  Success: geometry, magnet, undo, serialization, scoring, retrieval, decision, persistence, and prediction responsibilities are separated.
  Verification: `swift test` in `native/macos/AIStudioNative`.

## Parked Work

- [ ] App Store Connect upload remains blocked on owner Apple Developer credentials, signing identities, App Store Connect API key or app-specific password, and team configuration.

- [ ] Future iPadOS reuse remains a design requirement. Keep Swift-native subtitle, LoRA, deep policy, project I/O, timeline, and waveform logic reusable as Apple-platform core modules, with macOS-only UI/process/file-watcher/packaging code at the edges.
