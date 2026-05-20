# AI Subtitle Studio QA Test Case

이 문서는 Codex가 AI Subtitle Studio를 수정한 뒤 기능과 UI/UX를 임의로 바꾸지 않았는지 확인하기 위한 실앱 기준 QA 실행 규칙이다.

핵심 목적은 세 가지다.

- 모든 코드 변경은 함수 단위 자동 테스트와 실앱 UX 테스트로 검증한다.
- UI/UX 변경은 요청받은 범위 밖에서 발생하면 실패로 본다.
- 릴리즈 또는 사용자가 요청한 시점에는 전체 화면 스냅샷을 저장하고, 직전 기준선과 비교해 무단 UI 변경을 찾아 원복한다.

## 절대 규칙

- 임의 UI/UX 변경 금지: 버튼 위치, 색상, 크기, 문구, 여백, 메뉴 구조, 타임라인 표현, 단축키 동작, 팝업 동작은 사용자가 요청한 범위 밖에서 바꾸지 않는다.
- UX 테스트는 실제 앱 기준이다: 단위 테스트만 통과해도 실앱에서 재현하지 않으면 완료가 아니다.
- 스냅샷은 증거다: 기능 수정 전과 후의 주요 화면 PNG를 `output/manual_verification/` 아래에 남긴다.
- 원복 원칙: 스냅샷 비교에서 무단 UI 변경이 나오면 해당 변경을 만든 코드만 되돌린다. 사용자가 만든 다른 변경이나 unrelated dirty file은 건드리지 않는다.
- 중복 테스트 금지: 같은 코드 경로를 이미 커버하는 테스트가 있으면 같은 수준의 테스트를 반복하지 않고, 누락된 UX 또는 위험 경로만 추가한다.
- 긴 로그와 JSON은 채팅에 붙이지 않는다. 상세 결과는 `output/manual_verification/latest/` 또는 named run 폴더에 저장하고, 채팅에는 핵심 결과만 보고한다.

## 사용자 명령 매핑

사용자가 아래처럼 말하면 Codex는 추가 질문 없이 이 문서 기준으로 실행한다.

- `간단 test해줘`, `빠른 확인`, `quick test`: Quick Test 실행.
- `주요 test해줘`, `주요기능 점검`, `major test`: Major Test 실행.
- `full test해줘`, `전체 테스트`, `릴리즈 전 테스트`: Full Test 실행.
- `이전 버전과 ui 일치 확인해줘`: UI Snapshot Compare 실행.
- 영상 선택이 없으면 기본값은 Quick/Major는 `마카오`, Full은 `티니핑`이다.
- 사용자가 `마카오`, `x5`, `티니핑`을 지정하면 해당 fixture를 우선 사용한다.

## Fixture Registry

### Macau UX Fixture

용도: 빠른 UI/UX, 멀티클립, 에디터 조작, 타임라인 조작, 재시작 smoke.

- Folder: `/Users/u_mo_c/Downloads/마카오테스트`
- Primary five-video set:
- `/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217224203_0075_D.MP4`
- `/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217224602_0076_D.MP4`
- `/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217224716_0077_D.MP4`
- `/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217224900_0078_D.MP4`
- `/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217225132_0079_D.MP4`
- Fallback video:
- `/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217225355_0080_D.MP4`

### Tinyping Long-Flow Fixture

용도: 긴 영상, generation, roughcut, ETA, queue, memory, completion, editor restore.

- Project: `/Users/u_mo_c/Downloads/티니핑/티니핑_유스어드벤처.aissproj`
- Video: `/Users/u_mo_c/Downloads/티니핑/티니핑_유스어드벤처.MP4`
- Reference SRT: `/Users/u_mo_c/Downloads/티니핑/티니핑_유스어드벤처_완성.srt`

### X5 Accuracy Fixture

용도: STT 후보, subtitle accuracy, timing, VAD, LLM/LoRA/Deep gating, benchmark.

- Video: `/Users/u_mo_c/Downloads/ai_subtitle_studio/test video/X5_시승기_후반.MP4`
- Reference SRT: `/Users/u_mo_c/Downloads/ai_subtitle_studio/test video/X5_시승기_후반.srt`

## Output Layout

모든 자동 QA 결과는 아래 구조로 저장한다.

```text
output/manual_verification/latest/
  report.md
  report.json
  status.json
  notes.md
  snapshots/
    before/
    after/
    diff/
  logs/

output/manual_verification/ui_baselines/<version-or-label>/
  manifest.json
  home.png
  editor_idle.png
  editor_with_media.png
  timeline_zoomed.png
  subtitle_segment_edit.png
  smart_split_menu.png
  settings.png
  dictionary.png
  roughcut.png
  queue_processing.png
  completion.png
```

`latest/`는 항상 가장 최근 실행 결과를 가리키고, 릴리즈나 비교용 기준선은 `ui_baselines/<label>/`에 보존한다.

## Test Modes

### Quick Test

목표: 방금 수정한 코드가 깨지지 않았고, 앱 자동화/status/snapshot이 최소 동작하는지 빠르게 확인한다.

실행 조건:

- 작은 코드 수정.
- UI/UX 변경이 의도되지 않은 수정.
- status timeout, crash guard, 작은 refactor, 단일 함수 수정.

필수 단계:

1. 변경 파일 확인.
2. `py_compile` 또는 관련 모듈 syntax check.
3. 변경 파일과 직접 연결된 targeted unit test 실행.
4. 앱이 실행 중이면 `tools/appctl.py status` 확인.
5. 앱이 실행 중이면 현재 화면 snapshot 1장을 저장.
6. UI 관련 파일을 건드렸다면 before/after snapshot 차이를 확인한다.

기본 명령:

```bash
./venv/bin/python -m py_compile <changed-python-files>
./venv/bin/python -m unittest <targeted-test-modules> -q
./venv/bin/python tools/appctl.py --timeout 2 status
./venv/bin/python tools/remote_verify.py --timeout 2 capture --label quick_current --output-dir output/manual_verification/latest/snapshots/after
git diff --check --
```

합격 기준:

- syntax/test 실패 없음.
- `appctl status`가 timeout 없이 응답.
- snapshot 저장 성공.
- 의도하지 않은 UI 차이가 없음.

### Major Test

목표: 주요 기능과 에디터 UX가 실제 앱에서 유지되는지 확인한다.

실행 조건:

- UI/UX 관련 코드 수정.
- 에디터, 타임라인, 비디오 플레이어, 큐, 설정, 저장, 시작/정지, 자동화 브리지 수정.
- 사용자가 `주요 test해줘`라고 말한 경우.

필수 단계:

1. Quick Test 전체 실행.
2. 선택 fixture를 앱에 로드한다.
3. 홈, 큐, 에디터, 비디오 플레이어, 타임라인, 하단 메뉴, 설정, 사전, 프로젝트 정보 화면 snapshot을 저장한다.
4. 에디터 UX 핵심 조작을 자동 실행한다.
5. 직전 기준선이 있으면 snapshot compare를 실행한다.
6. 무단 UI 차이가 있으면 원인을 찾고 현재 작업에서 만든 변경만 원복한다.

기본 명령:

```bash
./venv/bin/python -m unittest \
  tests.test_app_command_bridge \
  tests.test_video_player_widget \
  tests.test_timeline_playhead_fit \
  tests.test_timeline_hit_targets \
  tests.test_timeline_paint_passes \
  tests.test_main_window_nonfatal \
  tests.test_cp03_cp04_status_ui \
  tests.test_sidebar_terminal_layout \
  -q

./venv/bin/python tools/remote_verify.py --timeout 4 editor-sequence \
  --label major_editor_ux \
  --open-media "/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217224203_0075_D.MP4" \
  --settle-sec 1.0 \
  --playhead-sec 1.5 \
  --playhead-center \
  --select-line 0 \
  --select-center \
  --actions snapshot begin-smart-split set-inline-cursor commit-inline-edit snapshot move-segment-left move-segment-right move-diamond merge-diamond snapshot \
  --cursor-pos 2 \
  --diamond-side right \
  --snapshot-each-step \
  --output-dir output/manual_verification/latest/major_editor_ux

./venv/bin/python tools/remote_verify.py --timeout 4 editor-sequence \
  --label major_menu_stt_lora \
  --open-project "/Users/u_mo_c/Downloads/ai_subtitle_studio/projects/DJI_20260217224203_0075_D.aissproj" \
  --settle-sec 1.0 \
  --actions open-dictionary capture-dictionary close-active-dialog open-settings capture-active-dialog close-active-dialog open-speaker-settings capture-active-dialog close-active-dialog stt-enable stt-disable lora-run-now lora-pause lora-resume snapshot \
  --output-dir output/manual_verification/latest/major_menu_stt_lora
```

에디터 UX 핵심 조작 체크리스트:

- 미디어 열기.
- 첫 프레임/총 프레임 표시 확인.
- 비디오 총 재생시간 표시 확인.
- 재생, 일시정지, 이전/다음, 빠른 이동 버튼 확인.
- playhead 이동과 타임라인 중앙 정렬 확인.
- 자막 세그먼트 선택, 더블클릭, inline edit 진입 확인.
- 자막 분할, 분할 후 편집 모드 진입 확인.
- 자막 삭제 메뉴, 임시자막 메뉴, 컨텍스트 메뉴 단일화 확인.
- 세그먼트 좌/우 경계 이동 확인.
- diamond 이동, cut boundary snapping, playhead 가림 방지 확인.
- 우측 끝 잔여 조각이 남지 않는지 확인.
- waveform, STT preview, VAD, roughcut lane, final subtitle lane 표시 확인.
- zoom in/out/reset, fit-to-view 확인.
- Lock Edit, 반복재생 상태 확인.
- 저장, 다시실행, 실행취소, 자동/캐시삭제 버튼 동작 확인.
- 홈으로 이동 후 다시 에디터 복귀 확인.
- 상태 카드, 큐 리스트, 진행률, 로그 패널 일치 확인.

합격 기준:

- 자동화 명령이 timeout 없이 완료.
- editor runtime snapshot에서 `segment_count`, `playhead_sec`, `active_seg_line`이 유효.
- 모든 UX 조작 후 앱이 crash 없이 살아 있음.
- 기준선과 다른 UI 차이가 있으면 변경 의도가 문서화되어 있어야 한다.

### Full Test

목표: 릴리즈 전 또는 큰 변경 후 전체 기능, 전체 함수 경로, 실앱 UX, 장시간 안정성을 검증한다.

실행 조건:

- 릴리즈 후보.
- native/C++/Swift 경로 변경.
- pipeline, STT, LLM, roughcut, project save/load, queue, timeline paint, video playback 등 cross-module 변경.
- 사용자가 `full test해줘`라고 말한 경우.

필수 단계:

1. clean-ish worktree 확인: unrelated dirty file은 기록만 하고 건드리지 않는다.
2. 전체 syntax check.
3. 전체 unit/integration test 또는 실패 범위를 분리한 full sweep.
4. 선택한 fixture로 full media pipeline 검증.
5. Macau 5개 영상 멀티클립/큐 UX 검증.
6. Tinyping long-flow 또는 X5 accuracy fixture 검증.
7. 모든 주요 UI 화면 snapshot 저장.
8. 이전 기준선과 snapshot compare.
9. 무단 UI 차이 원복.
10. 결과를 `output/manual_verification/latest/report.md`에 요약한다.

기본 명령:

```bash
./venv/bin/python -m compileall -q main.py core ui tools tests
./venv/bin/python -m unittest discover -s tests -p "test_*.py" -q
git diff --check --
```

Full media command:

```bash
./venv/bin/python tools/verify_full_media_pipeline.py \
  --media "/Users/u_mo_c/Downloads/티니핑/티니핑_유스어드벤처.MP4" \
  --mode high \
  --output-dir output/manual_verification/latest/full_media_tinyping
```

X5 accuracy command:

```bash
./venv/bin/python tools/verify_full_media_pipeline.py \
  --media "/Users/u_mo_c/Downloads/ai_subtitle_studio/test video/X5_시승기_후반.MP4" \
  --mode high \
  --output-dir output/manual_verification/latest/full_media_x5
```

Macau five-video UX command:

```bash
./venv/bin/python tools/appctl.py --timeout 4 queue-files \
  "/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217224203_0075_D.MP4" \
  "/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217224602_0076_D.MP4" \
  "/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217224716_0077_D.MP4" \
  "/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217224900_0078_D.MP4" \
  "/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217225132_0079_D.MP4"
```

합격 기준:

- full test failure가 있으면 실패한 test module, 실패 원인, 관련 파일을 기록한다.
- real app이 media load, generation start, status polling, editor UX sequence, snapshot capture를 완료한다.
- `status`가 처리 중에도 timeout 없이 응답한다.
- final subtitle count, raw subtitle count, completion score, resource peak가 report에 기록된다.
- 무단 UI diff가 0이거나, 의도된 변경으로 사용자 승인 기록이 있어야 한다.

## UI Snapshot Baseline

릴리즈 전 또는 사용자가 요청한 시점에 모든 주요 화면을 기준선으로 저장한다.

기준선 생성 명령:

```bash
BASELINE="output/manual_verification/ui_baselines/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BASELINE"

./venv/bin/python tools/remote_verify.py --timeout 4 capture \
  --label home \
  --output-dir "$BASELINE"

./venv/bin/python tools/remote_verify.py --timeout 4 editor-sequence \
  --label editor_with_media \
  --open-media "/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217224203_0075_D.MP4" \
  --settle-sec 1.0 \
  --actions snapshot \
  --snapshot-each-step \
  --output-dir "$BASELINE/editor_with_media"

./venv/bin/python tools/remote_verify.py --timeout 4 editor-sequence \
  --label editor_segment_edit \
  --playhead-sec 1.5 \
  --select-line 0 \
  --actions begin-smart-split snapshot \
  --snapshot-each-step \
  --output-dir "$BASELINE/editor_segment_edit"
```

필수 snapshot 목록:

- home.
- queue idle.
- queue processing.
- editor idle.
- editor with media.
- video player controls.
- timeline full width.
- timeline zoomed.
- subtitle segment selected.
- subtitle segment inline edit.
- context menu.
- smart split/edit menu.
- settings main.
- AI settings.
- dictionary.
- project info.
- roughcut view.
- completion state.
- error/warning dialog when intentionally triggered by test fixture.

## UI Snapshot Compare

사용자가 `이전 버전과 ui 일치 확인해줘`라고 말하면 다음 절차를 실행한다.

1. 비교 대상 baseline 폴더를 찾는다.
2. 현재 앱에서 같은 화면, 같은 fixture, 같은 playhead/sec, 같은 window size로 snapshot을 다시 찍는다.
3. PNG pixel diff와 파일 크기, 해상도, 주요 crop 영역 차이를 기록한다.
4. 허용 diff와 무단 diff를 구분한다.
5. 무단 diff는 관련 코드 변경을 찾아 현재 작업에서 만든 변경만 원복한다.
6. 원복 후 같은 compare를 다시 실행한다.

허용 diff:

- 영상 프레임 자체가 시간에 따라 달라진 경우.
- 진행률, 시간, frame number, CPU/RAM, log timestamp처럼 runtime 값이 바뀐 경우.
- 사용자가 명시적으로 승인한 UI 변경.

무단 diff:

- 버튼 추가/삭제.
- 메뉴 구조 변경.
- 색상/테두리/강조색 변경.
- spacing, margin, height, width 변경.
- 폰트 크기/굵기 변경.
- 레이블 문구 변경.
- timeline lane 높이/위치/색상 변경.
- playhead/diamond/segment marker 시각 동작 변경.
- video controls 배경, 정렬, hit area 변경.

compare 결과 파일:

```text
output/manual_verification/latest/ui_compare/
  compare_report.md
  compare_report.json
  changed_files.txt
  before/
  after/
  diff/
```

## Function-Level Coverage Rule

사용자가 말한 "모든 함수 테스트"는 다음 계약으로 해석한다.

- Python 함수/클래스: 기존 unit test 또는 새 targeted unit test로 실행 경로를 보장한다.
- Qt signal/slot: `tests/test_*`에서 fake object로 호출하거나 실앱 automation으로 호출한다.
- UX 함수: `tools/appctl.py` 또는 `tools/remote_verify.py` 명령으로 실앱에서 호출한다.
- native/C++/Swift 함수: Python fallback과 native path를 같은 input/output parity test로 검증한다.
- pipeline 함수: small fixture 또는 real media fixture로 stage별 산출물을 확인한다.
- UI paint 함수: offscreen paint test와 실앱 snapshot을 둘 다 확인한다.

변경한 함수에 테스트가 없으면 완료가 아니다. 반드시 다음 중 하나를 한다.

- 기존 test module에 해당 함수의 regression case 추가.
- 새 `tests/test_<area>.py` 추가.
- 실앱 automation scenario에 해당 기능을 추가.
- 테스트 불가능한 이유와 수동 확인 절차를 `output/manual_verification/latest/notes.md`에 기록.

## Coverage Matrix

| Area | Unit/Integration Tests | Real App UX Test | Snapshot Required |
| --- | --- | --- | --- |
| App startup/shutdown | `tests.test_startup_diagnostics`, `tests.test_main_window_nonfatal`, `tests.test_native_macos_exit` | launch, status, quit while idle/processing | home, shutdown-safe status |
| App command/status | `tests.test_app_command_protocol`, `tests.test_app_command_bridge` | `appctl status`, `remote_verify capture` | current screen |
| Home/sidebar/queue | `tests.test_cp03_cp04_status_ui`, `tests.test_sidebar_terminal_layout`, `tests.test_queue_signal_payloads` | queue-files, progress, completion | home, queue idle, queue processing |
| Video player | `tests.test_video_player_widget`, `tests.test_audio_display` | play/pause/seek/frame counter | video controls |
| Timeline paint/layout | `tests.test_timeline_paint_passes`, `tests.test_timeline_render_cache`, `tests.test_timeline_layout_constants` | zoom, scroll, playhead, edge artifact check | timeline full, timeline zoomed |
| Segment editing | `tests.test_timeline_playhead_fit`, `tests.test_timeline_hit_targets`, `tests.test_editor_split_undo` | select, double click, split, inline edit, move boundary | selected, inline edit, split menu |
| Context menu | `tests.test_context_menu_bounds`, `tests.test_popup_dismiss` | right click / menu action automation | context menu |
| STT/VAD/audio | `tests.test_stt_ensemble`, `tests.test_stt_recheck_service`, `tests.test_stt_vad_ensemble`, `tests.test_media_processor_overlap` | generation smoke | queue processing, editor preview |
| LLM/LoRA/quality | `tests.test_codex_provider`, `tests.test_subtitle_quality_pipeline`, `tests.test_lora_*` | high mode full media | completion |
| Roughcut | `tests.test_roughcut_*`, `tests.test_editor_roughcut_draft` | post-generation roughcut | roughcut view |
| Project save/load | `tests.test_project_*`, `tests.test_editor_srt_open_refresh` | open project, save, reopen | editor restored |
| Settings/dictionary | `tests.test_settings_*`, `tests.test_settings_dictionary` | open settings/dictionary | settings, dictionary |
| Native acceleration | `tests.test_native_*`, `tests.test_runtime_optimization_profile` | full media performance sample | report only |

## Automatic Run Recipes

### Quick: default

```bash
./venv/bin/python -m py_compile main.py ui/main/app_command_bridge.py ui/dialogs/qml_popup.py ui/main/main_signals.py
./venv/bin/python -m unittest tests.test_app_command_bridge tests.test_qml_popup_guard tests.test_main_window_nonfatal -q
./venv/bin/python tools/appctl.py --timeout 2 status
./venv/bin/python tools/remote_verify.py --timeout 2 capture --label quick --output-dir output/manual_verification/latest/quick
git diff --check --
```

### Major: Macau UX

```bash
./venv/bin/python -m unittest \
  tests.test_app_command_bridge \
  tests.test_video_player_widget \
  tests.test_timeline_playhead_fit \
  tests.test_timeline_hit_targets \
  tests.test_timeline_paint_passes \
  tests.test_context_menu_bounds \
  tests.test_editor_split_undo \
  tests.test_cp03_cp04_status_ui \
  tests.test_sidebar_terminal_layout \
  -q

./venv/bin/python tools/remote_verify.py --timeout 4 editor-sequence \
  --label macau_major_ux \
  --open-media "/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217224203_0075_D.MP4" \
  --settle-sec 1.0 \
  --playhead-sec 1.5 \
  --playhead-center \
  --select-line 0 \
  --select-center \
  --actions snapshot begin-smart-split set-inline-cursor commit-inline-edit snapshot move-segment-left move-segment-right move-diamond merge-diamond snapshot \
  --cursor-pos 2 \
  --diamond-side right \
  --snapshot-each-step \
  --output-dir output/manual_verification/latest/macau_major_ux
```

### Full: Tinyping

```bash
./venv/bin/python -m compileall -q main.py core ui tools tests
./venv/bin/python -m unittest discover -s tests -p "test_*.py" -q
./venv/bin/python tools/verify_full_media_pipeline.py \
  --media "/Users/u_mo_c/Downloads/티니핑/티니핑_유스어드벤처.MP4" \
  --mode high \
  --output-dir output/manual_verification/latest/full_tinyping
git diff --check --
```

### Full: X5

```bash
./venv/bin/python -m compileall -q main.py core ui tools tests
./venv/bin/python -m unittest discover -s tests -p "test_*.py" -q
./venv/bin/python tools/verify_full_media_pipeline.py \
  --media "/Users/u_mo_c/Downloads/ai_subtitle_studio/test video/X5_시승기_후반.MP4" \
  --mode high \
  --output-dir output/manual_verification/latest/full_x5
git diff --check --
```

### Full: Macau 5 Videos

```bash
./venv/bin/python -m compileall -q main.py core ui tools tests
./venv/bin/python -m unittest discover -s tests -p "test_*.py" -q
./venv/bin/python tools/appctl.py --timeout 4 queue-files \
  "/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217224203_0075_D.MP4" \
  "/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217224602_0076_D.MP4" \
  "/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217224716_0077_D.MP4" \
  "/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217224900_0078_D.MP4" \
  "/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217225132_0079_D.MP4"
./venv/bin/python tools/remote_verify.py --timeout 4 capture --label macau_queue --output-dir output/manual_verification/latest/macau_queue
git diff --check --
```

## Failure Handling

테스트 실패 시 Codex는 다음 순서로 처리한다.

1. 실패를 숨기지 않는다.
2. 실패가 code regression인지, fixture 문제인지, 환경 문제인지 분류한다.
3. code regression이면 가장 작은 범위로 수정한다.
4. UI snapshot diff가 무단 변경이면 관련 UI 코드를 원복한다.
5. 원복 후 같은 테스트를 다시 실행한다.
6. 남은 실패가 있으면 `output/manual_verification/latest/notes.md`에 blocker로 남긴다.

## Final Report Format

테스트 완료 후 채팅 보고는 짧게 한다.

필수 항목:

- 실행 모드: Quick / Major / Full.
- 선택 fixture: Macau / Tinyping / X5.
- 결과: pass / fail / blocked.
- 저장 위치: `output/manual_verification/latest/...`.
- UI diff: 없음 / 의도된 변경 / 무단 변경 원복 완료 / blocker.
- 남은 위험: 있으면 1-3줄.

## Maintenance Rule

새 기능 또는 새 UX가 추가되면 이 문서도 같이 갱신한다.

- 새 버튼/메뉴/모드가 추가되면 snapshot 목록에 추가한다.
- 새 automation command가 추가되면 `Automatic Run Recipes`에 추가한다.
- 새 native path가 추가되면 parity test 이름을 `Coverage Matrix`에 추가한다.
- 새 fixture가 안정화되면 `Fixture Registry`에 추가한다.
- UI/UX 변경을 허용받은 경우 기준선 snapshot을 새로 만든다.

## 요청 기반 추가 UX 테스트 케이스 (자동 확장 정책 포함)

아래 항목이 `test_case.md`에 없으면 실행 즉시 항목을 추가한 뒤 full test에 반영한다.

1. 자막 열기 후 자막 에디터 기능
- 방법: `open-srt`로 타임스탬프 파일 열기 → 에디터 진입 여부 확인 → 편집 가능한 모드 진입 확인.
- 통과: `editor_open=true`, `editor_media_path`에 SRT 경로 기록, 즉시 에디터 UI 스냅샷 저장.
- 실패 시: `action`를 `검토필요`로 분리하고 `ACTION_ITEMS.md`에 메뉴얼 검토 요청.

2. 영상 열기 후 자막 생성 (fast/auto/high)
- 방법: 마카오 5개 또는 티니핑 60초 구간 기반 fixture에서 각 모드 `start-current-pipeline` 실행.
- 통과: `tinyping_full_verify.json` 결과 status=ok, final segment 개수 유효.
- 실패 시: `pipeline/roughcut` 로그와 `start_current_pipeline.json`을 함께 보존.

3. 멀티클립 열기 후 자막 생성
- 방법: 3~5개 영상의 `queue-files` 실행 후 큐 완료/실패 상태를 실시간 모니터링.
- 통과: `status.status_snapshot_fallback` 없이 모든 row가 done 또는 명시적 에러 처리.
- 실패 시: `queued_until_main_window_ready`/`app_unreachable` 포함 여부를 분리 분석.
- 고도화: `start accepted`, 앱 내부 처리 로그, `all_done` 수렴, 최종 queue row snapshot을 각각 분리한 4단계 assertion으로 쪼갠다.

4. 화면 간 전환(홈, 에디터, 러프컷, 숏폼)
- 방법: `show-home`, `open-project`, `open-media`, `start-current-roughcut` 순차 실행.
- 통과: 각 화면 전환마다 스냅샷 저장 및 `editor_state`/`editor_open` 상태 변화가 정상.
- 실패 시: 화면별 `status` 및 스냅샷 실패 원인을 `notes`에 기록.

5. 모든 메뉴 1회 및 LoRA 시작/종료
- 방법: 열린 상태에서 사전/셋팅/딕셔너리/화자/LoRA 시작·종료 명령을 각 1회 실행.
- 통과: 명령 응답이 ok이고 메뉴 화면이 최소 1회 이상 캡처됨.
- 실패 시: `command`, `error`, `message`를 메뉴별로 분리해 action item 등록.
- 권장 자동화: `remote_verify --actions open-dictionary capture-dictionary close-active-dialog open-settings capture-active-dialog close-active-dialog open-speaker-settings capture-active-dialog close-active-dialog stt-enable stt-disable lora-run-now lora-pause lora-resume snapshot`
- 고도화: settings/speaker/dictionary popup 캡처, STT on/off status diff, `personalization-idle run-now`, `pause`, `resume`를 별도 케이스로 나누고 LoRA는 앱 로그 증거도 함께 수집한다.

6. 시작/종료 테스트
- 방법: 앱 실행 직후 `status` 후 종료 신호(quit) 실행, 재실행 시 자동복구 확인.
- 통과: 종료 요청 후 앱 상태가 종료되고, 재실행 시 UI가 정상으로 돌아와 fixture를 다시 열 수 있음.
- 실패 시: 종료 전후 로그 타임라인으로 크래시/락 원인 분기.

7. 프로젝트 저장, 자막 저장, 자막 출력, 자막 영상 출력
- 방법: `open-project` → `save-project` → `save-subtitles` → `export-subtitles <artifact/export.srt>` → `export-subtitle-video` → 최종 snapshot 저장.
- 통과: project, saved SRT, manual export SRT, subtitle MOV가 모두 존재하고 bytes가 0보다 크다. 가능하면 project/MOV는 mtime 또는 bytes 변화도 함께 남긴다.
- 실패 시: `unknown_command`, `subtitle_outputs_missing`, render 실패를 분리하고 각 단계 stdout/json을 별도 artifact로 남긴다.
- 고도화: `변경사항이 없습니다` 경로에서도 기존 SRT 경로를 역추론해 파일 검증을 계속하고, final status의 `status_snapshot_fallback` 관측 여부를 같이 기록한다.

8. 자막 에디터 기능(단축키, 기본 조작)
- 방법: `editor-set-playhead`, `editor-select-segment`, `editor-begin-smart-split`, `editor-set-inline-cursor`, `editor-commit-inline-edit` 실행.
- 통과: 7개 핵심 조작이 연쇄 성공하고 스냅샷에서 편집 컨텍스트가 반영.
- 실패 시: 실패 단계 하나씩 분리해 재실행 루프 추가.
- 고도화: 액션 실행 전 `smart_split_ready`, `inline_edit_active`, `active_seg_line`을 status로 먼저 확인해 precondition failure와 실제 기능 실패를 분리한다.
- 고도화: `open-project` 직후 최소 2초, `set-playhead` 직후 최소 1초 settle을 두고 compact action path와 status-heavy path를 분리한다. command 사이에 초기화가 겹치면 playhead가 `0.0`으로 되감길 수 있다.

9. 자막 세그먼트 에디터/팝업 메뉴
- 방법: 선별 시퀀스(`editor-select-segment`, `editor-move-segment-left/right`, `editor-move-diamond`, `editor-merge-diamond`) + 팝업 메뉴 호출/닫기.
- 통과: 메뉴가 열리고 닫히며 시각적 편집 컨텍스트 반영.
- 실패 시: 팝업 호출 명령 유무부터 검증하도록 test_case 자체를 확장.

10. 임의 편집 후 컷 경계 및 플레이헤드 확인
- 방법: 재생 헤드 이동 → 세그먼트 분할/이동/병합 전후 playhead/segment_count/gap_count 비교.
- 통과: 경계값이 음수/누락/역전되지 않음.
- 실패 시: `set-playhead` 직후와 작업 후 diff를 artifact로 저장.

11. 지디오 재생 + 비디오 메뉴
- 방법: play/pause/seek 및 비디오 메뉴 열기/닫기를 반복 실행.
- 통과: 각 동작 후 status의 playback/log 상태가 즉시 갱신.
- 실패 시: `playback_play`, `playback_pause` 타임아웃 원인 기록.

12. 화자 관련 메뉴 테스트
- 방법: 화자 패널/트랙 설정 토글 후 자막/타임라인 반응 점검.
- 통과: 화자 토글이 세그먼트 라벨에 반영.
- 실패 시: 화자 메뉴 자체의 command id와 응답을 우선 분리.

13. STT 모드 테스트
- 방법: STT1/2, 다중모드 전환 메뉴 또는 설정에서 모드 변경 후 동일 구간 생성 결과 비교.
- 통과: 모드별 산출물(`final.srt`/메타) 비교에 기대값이 존재.
- 실패 시: 모드 토글 경로가 불명확하면 커맨드 레이어까지 명세 추가.
- 고도화: 토글 직후 `editor_stt.enabled/state/recording/vad_running` status diff를 남기고, 녹음 시작/정지 시나리오와 단순 토글 시나리오를 분리한다.
- 고도화: LoRA `run-now/pause/resume`는 즉시 ack와 settle 후 status를 분리 기록한다. 직후 status가 fallback이면 3초 후 재조회해 최종 runtime(`active`, `last_action`, `last_result`)을 따로 남긴다.

### 테스트 케이스 자동 추가 규칙

- 실행 중 항목이 빠진 경우 해당 항목을 먼저 `test_case.md`에 추가하고, 테스트를 즉시 1회 이상 실행한다.
- 항목은 실패, 검토 필요, 통과를 각각 별도 라인에 남기고 다음 실행에서 회귀 판정 근거로 재사용한다.

### 테스트 케이스 고도화 메모 - 2026-05-20

- 장시간 작업은 `accepted 응답`과 `실제 완료/중단 상태`를 분리 기록한다. 예: 멀티클립, LoRA.
- 편집 시퀀스는 precondition snapshot(`smart_split_ready`, `inline_edit_active`) 없이 바로 실패로 합치지 않는다.
- popup/overlay는 command 결과만 보지 말고 실제 PNG 저장 여부까지 통과 조건에 포함한다.
- 저장/내보내기는 파일 존재성 검증이 없으면 통과로 올리지 않는다.
- 저장 생략 경로도 실패로 뭉개지지 않게 기존 SRT/MOV 경로 fallback과 실제 파일 stat을 같이 남긴다.

### One-command QA runner 실행 레시피 - 2026-05-20

1. `quick`
- 방법: `./venv/bin/python tools/qa_suite_runner.py quick`
- 목적: app bootstrap과 editor smoke를 한 번에 확인한다.
- 통과: `suite_result.json`의 `failed_count=0`
- 산출물: `output/manual_verification/latest/qa_suite_quick_*`

2. `major`
- 방법: `./venv/bin/python tools/qa_suite_runner.py major`
- 목적: Macau UX 핵심 회귀 4개를 한 번에 확인한다.
- 포함 시나리오:
  - `editor_compact_macau`
  - `video_menu_macau`
  - `save_export_macau`
  - `menu_stt_lora_macau`
- 통과: `scenario_count=4`, `failed_count=0`
- 산출물: `output/manual_verification/latest/qa_suite_major_*`

3. `full`
- 방법: `./venv/bin/python tools/qa_suite_runner.py full`
- 목적: `major` + Tinyping 60초 `fast/auto/high`를 한 번에 확인한다.
- 포함 시나리오:
  - Macau UX 4개
  - `tinyping_fast_60s`
  - `tinyping_auto_60s`
  - `tinyping_high_60s`
- 통과: `scenario_count=7`, `failed_count=0`
- 산출물: `output/manual_verification/latest/qa_suite_full_*`

4. 현재 runner 안정화 규칙
- app sequence는 `major/full`에서 scenario 시작 전 app prepare를 수행한다.
- 실행체는 최신 workspace 코드가 반영된 `dist/macos/AI Subtitle Studio.app`를 우선 사용한다.
- `editor_compact_macau`는 고정 `1.5초` 대신 현재 `editor_runtime.active_segment`에서 동적 playhead를 계산한다.
- `move_diamond`/`merge_diamond`는 현재 `diamond_left/right`의 `boundary_sec`를 기준으로 command를 조립한다.
- `full_media`는 stdout 전체가 아니라 마지막 JSON line을 우선 파싱한다.

5. 고도화 메모
- 큰 command surface 변경 뒤에는 `packaging/macos/build_app_bundle.sh`로 bundle을 먼저 갱신한다.
- `suite_result.json`, `suite_result.md`, `suite_manifest.json`을 같은 artifact 폴더에서 함께 보관한다.
- `full`에서 실패가 나면 먼저 `app_sequence` 실패인지 `Tinyping full_media` 실패인지 분리하고, `full_media`는 `result_path`와 `logs/run.stdout`를 같이 본다.
