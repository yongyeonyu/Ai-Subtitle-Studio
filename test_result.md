# 자동화-4 전체 UX 테스트 결과

## v04.00.13 selective STT2 recursion regression release - 2026-05-22

- 실행 모드: Targeted + X5 High real-media + Full
- 결과:
  - Targeted: pass
  - X5 High 3-minute: pass, `output/manual_verification/latest/20260522_x5_high_release_regression_fix`
  - Full: pass, `output/manual_verification/latest/qa_suite_full_20260522_081710`
- 수정/확인 항목:
  - Apple Silicon runtime plan 적용 후 `_fast_mode_overrides`를 다시 반영하도록 바꿔 pass-specific STT disable override가 살아남게 했다.
  - 그 결과 `선택 STT2 재검사`가 `_fast_stt2_recheck` 내부에서 자기 자신을 다시 재기동하던 재귀 경로를 차단했다.
  - UI/UX, 라벨, 레이아웃, 단축키, 자막 품질 정책은 변경하지 않았다.
- 단위/가드:
  - `./venv/bin/python -m unittest tests.test_audio_presets tests.test_media_processor_overlap.MediaProcessorOverlapTests.test_native_batch_refine_routes_precision_rechecks_after_full_stt1_pass -q`: pass (`49 tests OK`)
  - `./venv/bin/python -m py_compile core/audio/media_processor.py tests/test_audio_presets.py`: pass
  - `git diff --check -- core/audio/media_processor.py tests/test_audio_presets.py`: pass
- 실영상 검증:
  - `./venv/bin/python tools/verify_full_media_pipeline.py --media '/Users/u_mo_c/Downloads/ai_subtitle_studio/test video/X5_시승기_후반.MP4' --mode high --duration-sec 180 --output-dir output/manual_verification/latest/20260522_x5_high_release_regression_fix`
  - 결과: pass
  - 요약: `total_elapsed_sec=182.697`, `pipeline_elapsed_sec=168.115`, `peak_rss_bytes=652050432`, `final/raw=54/52`
  - 이전 실패 원인인 `_fast_stt2_recheck/.../_fast_stt2_recheck/...` 중첩과 `Failed to load audio: Interrupted system call`이 재발하지 않았다.
- full QA:
  - `./packaging/macos/build_app_bundle.sh`: pass
  - `./venv/bin/python tools/qa_suite_runner.py full`: pass
  - scenario count `5`, failed `0`
- 분류:
  - code regression: Apple Silicon runtime plan이 pass-specific STT override를 덮어써 recursive selective recheck를 유발.
  - fixture drift: 없음.
  - environment-bundle issue: 없음.
- 코드 수정 여부: 있음.
- 문서 반영 여부: 있음. `RELEASE_v04.00.13.md`, `README.md`, `AGENTS.md`, `test_result.md`.
- 남은 위험:
  - long High 경로는 여전히 memory pressure `critical`에 들어갈 수 있으므로, 이후 최적화는 메모리 압박과 STT2/word precision wall-clock을 별도로 다뤄야 한다.

## QA fixture rule update - 2026-05-21

- 실행 모드: Targeted
- 결과: pass
- 변경/확인 항목:
  - `tools/qa_suite_runner.py full`에서 기본 full-media 시나리오를 Tinyping 60초 fast/auto/high 3건에서 X5 high 3분 rolling 1건으로 변경.
  - Tinyping은 기본 QA에서 제외하고, 사용자가 명시 요청한 long-flow 수동 검증으로만 사용하도록 `AGENTS.md`, `test_case.md`, `README.md` 규칙을 갱신.
- 단위/가드:
  - `./venv/bin/python -m unittest tests.test_qa_suite_runner -q`: pass
  - `./venv/bin/python -m py_compile tools/qa_suite_runner.py tests/test_qa_suite_runner.py`: pass
  - `git diff --check -- tools/qa_suite_runner.py tests/test_qa_suite_runner.py test_case.md README.md AGENTS.md`: pass
- 실영상 검증:
  - 실행하지 않음. 이번 변경은 runner 구성/문서 규칙 변경이며, 무거운 Tinyping 검증은 기본 테스트에서 제외했다.

## 영상 오픈 전처리 지연 축소 - 2026-05-21 21:52~21:55

- 실행 모드: Targeted + 실앱 Tinyping open-media smoke
- 결과: pass
- 수정/확인 항목:
  - 영상 오픈 직후 720p HEVC preview proxy ffmpeg 빌드를 시작하지 않도록 했다.
  - single media waveform 로드는 영상 오픈 직후가 아니라 `시작` 클릭 후 파이프라인 시작 피드백이 표시된 다음 시작하도록 미뤘다.
  - 자막 품질/STT/LLM/VAD 알고리즘은 변경하지 않았다.
- 단위/가드:
  - `tests.test_project_segment_reload.ProjectSegmentReloadTests.test_native_open_media_bootstrap_defers_waveform_until_start`: pass
  - `tests.test_video_player_widget.VideoPlayerWidgetTests.test_deferred_probe_load_does_not_start_preview_proxy_build`: pass
  - `tests.test_cp03_cp04_status_ui.Cp03Cp04StatusUiTests.test_start_pipeline_marks_processing_before_cut_prescan`: pass
  - 관련 6 targeted tests: pass
  - `py_compile`: pass
  - `git diff --check`: pass
- 실앱 검증:
  - Tinyping `open-media` 응답 `0.284s`.
  - 시작 전 `preview_720p_hevc` / waveform 관련 ffmpeg 프로세스 없음.
  - 비디오 source는 원본 MP4로 로드되고 `video_duration_ms=1450265` 확인.
- 저장 위치:
  - `output/manual_verification/latest/media_open_before_start_deferred_prep.png`
- 분류:
  - code regression: 없음. 시작 전 불필요한 UI 편의 준비 작업을 지연시킨 UX/performance 개선.
  - fixture drift: 없음.
  - environment-bundle issue: 없음.
- 코드 수정 여부: 있음.
- 문서 반영 여부: 있음. `test_result.md`.
- 남은 위험:
  - 시작 직후 waveform worker가 자막 생성과 겹칠 수 있으므로, 장시간 high benchmark에서 리소스 경합이 보이면 waveform을 생성 완료 후 idle로 더 늦추는 후속 후보가 된다.

## 비디오 재생/오픈 직후 플레이헤드 레이스 회귀 수정 - 2026-05-21 21:09~21:11

- 실행 모드: Targeted + 실앱 Tinyping project smoke
- 결과: pass
- 수정/확인 항목:
  - 손상된 720p HEVC preview proxy cache가 있으면 QMediaPlayer duration이 `0`으로 떨어져 생성 후 재생이 멈출 수 있던 문제를 수정했다.
  - 프로젝트 오픈 직후 `editor-set-playhead`가 들어오면 지연 workspace restore가 저장된 마지막 위치로 다시 덮던 race를 수정했다.
  - `status` / `guided-subtitle-status`는 새 코드 재시작 후 `editor_runtime.video_*` 진단값을 정상 반환했다.
- 단위/가드:
  - `tests.test_video_preview_proxy`, 관련 `tests.test_video_player_widget`: pass
  - `tests.test_workspace_restore`: pass
  - `tests.test_app_command_bridge`: pass (`60 tests OK`)
  - `py_compile`: pass
  - `git diff --check`: pass
- 실앱 검증:
  - Tinyping project open 후 즉시 `editor-set-playhead 977.91 --center`.
  - 1.2초 후 `playhead_sec=977.910267`, `video_position_ms=977910`, `video_duration_ms=1450281`.
  - 이어서 재생 확인: `977.91s -> 978.39s`로 진행.
- 저장 위치:
  - `output/manual_verification/latest/video_playback_after_generation_fixed.png`
  - `output/manual_verification/latest/open_project_set_playhead_race_fixed.png`
- 분류:
  - code regression: preview proxy cache validation 누락, open-project 지연 restore와 즉시 seek race.
  - fixture drift: 없음.
  - environment-bundle issue: 없음.
- 코드 수정 여부: 있음.
- 문서 반영 여부: 있음. `test_result.md`.
- 남은 위험:
  - 생성 직후 아주 바쁜 STT/LLM 구간의 status fallback은 생존성 우선 정책을 유지한다. 상세 최신성은 command별 직접 응답과 artifact로 확인한다.
  - `idea_item.md` active queue는 현재 없음.

## idea_item 전체 실행 재검증 및 큐 종료 - 2026-05-21 12:15~12:19

- 실행 모드: Quick / Major / Full + Macau/X5/Tinyping benchmark
- 결과:
  - Quick: pass, `output/manual_verification/latest/qa_suite_quick_20260521_121518`
  - Major: pass, `output/manual_verification/latest/qa_suite_major_20260521_121601`
  - Full: pass, `output/manual_verification/latest/qa_suite_full_20260521_121658`
- 추가 benchmark:
  - Macau fast repeat10: pass, `output/manual_verification/latest/idea_full_execute_20260521-rerun/macau_fast_repeat10/repeat_summary.json`
    - pipeline avg/min/max `7.572s/7.427s/7.849s`, final segment `5` 유지, stage trim avg `6.0`
  - X5 modes repeat10 quality gate: pass, `output/manual_verification/latest/idea_full_execute_20260521-rerun/x5_modes_repeat10_current/repeat_summary.md`
    - `mode_high_piecewise_drift`: gate `10/10`, avg `43.693s`, p95 `44.338s`, quality `72.989`, final segments `24`
    - `mode_fast`: gate `0/10`, avg `10.250s`, p95 `11.410s`, quality `71.514`, final segments `17`
  - Tinyping long high: pass, `output/manual_verification/latest/idea_full_execute_20260521-rerun/tinyping_long_high/tinyping_full_verify.json`
    - media `24:10`, total `602.634s`, pipeline `574.298s`, peak RSS `4205363200`, final/raw `385/424`, rollback `0`
- 최종 선택:
  - 품질 동일 최종 후보는 `mode_high_piecewise_drift`.
  - `mode_fast`는 Fast 모드 속도 후보로는 유지하지만 X5 reference 품질 gate 실패 때문에 품질 동일 기본 알고리즘으로 승격하지 않는다.
- 분류:
  - regression: 없음
  - fixture drift: 없음
  - environment-bundle issue: 없음
- 코드 수정 여부: 없음. 이번 단계는 benchmark/QA refresh와 실행 큐 문서 종료.
- 문서 반영 여부: 있음. `idea_item.md`, `ACTION_ITEMS.md`, `NATIVE_LIB_PLAN.md`, `README.md`, `test_result.md`, `waste_action_item.md`, `lesson_n_learned.md`.
- 남은 위험:
  - Tinyping long high는 성공했지만 runtime pressure snapshot이 `critical`을 기록했다. 장시간 high에서 memory pressure 관찰은 계속 필요하다.
  - UI snapshot diff 자동 비교기는 별도 전용 도구가 아니라 공식 `quick/major/full` screenshot artifact 기준으로 확인했다.

## Phase 8 최종 full QA 및 알고리즘 선택 - 2026-05-21 11:37~11:39

- 실행 모드: Full
- 결과:
  - Full: pass, `output/manual_verification/latest/qa_suite_full_20260521_113718`
  - 최종 요약: `output/manual_verification/latest/idea_full_execute_20260521-1137/summary.md`
- 최종 `full` scenario:
  - `editor_compact_macau`: pass
  - `video_menu_macau`: pass
  - `save_export_macau`: pass
  - `menu_stt_lora_macau`: pass
  - `tinyping_fast_60s`: pass (`total_elapsed_sec=22.563`, `pipeline_elapsed_sec=10.015`, `peak_rss_bytes=460652544`, `final/raw=18/15`)
  - `tinyping_auto_60s`: pass (`total_elapsed_sec=43.851`, `pipeline_elapsed_sec=9.993`, `peak_rss_bytes=788611072`, `final/raw=18/15`)
  - `tinyping_high_60s`: pass (`total_elapsed_sec=25.689`, `pipeline_elapsed_sec=25.596`, `peak_rss_bytes=1299939328`, `final/raw=16/16`)
- 최종 선택:
  - X5 10회 품질 gate를 기준으로 품질 동일 최종 후보는 `mode_high_piecewise_drift`.
  - `mode_fast`는 빠르지만 품질 gate 실패로 기본 알고리즘 승격 제외.
  - STT1/STT2 full-parallel과 native policy helper default 승격은 `waste_action_item.md` 기준으로 폐기 유지.
- 코드 수정 여부: 없음. 최종 검증/문서 정리.
- 문서 반영 여부: 있음. `idea_item.md`, `README.md`, `test_result.md`.
- 남은 위험:
  - Tinyping long high 1회와 별도 UI snapshot diff 자동화는 시간상 이번 최종 full에는 포함하지 못했다.

## Phase 7 도움말 QA coverage 매핑 - 2026-05-21 11:35

- 실행 모드: Targeted
- 결과:
  - 단위/가드: pass
- 코드/문서 반영:
  - 기존 도움말 UI 순서는 유지하고 `HELP_QA_COVERAGE` 데이터만 추가했다.
  - `tests.test_help_dialog`가 모든 도움말 탭에 QA profile, owner, artifact 매핑과 owner 경로 존재 여부를 검증한다.
  - `README.md` 최신 quick baseline을 `qa_suite_quick_20260521_113130`으로 갱신했다.
  - `test_case.md` coverage matrix에 Help/manual QA map 행을 추가했다.
- 단위/가드:
  - `tests.test_help_dialog`: pass
- 분류:
  - 실패 없음.
  - code regression/fixture drift/environment-bundle issue 없음.

## Phase 6 타임라인 silent fallback 로그화 - 2026-05-21 11:26

- 실행 모드: Targeted
- 결과:
  - 단위/가드: pass
  - Quick: pass, `output/manual_verification/latest/qa_suite_quick_20260521_113130`
- 코드 반영:
  - `TimelineCanvas`의 viewport clip 실패와 voice-activity lane refresh 실패가 더 이상 조용히 묻히지 않고 key별 one-shot WARN으로 남는다.
  - 복구 동작은 유지했다. viewport clip 실패 시 full canvas repaint, voice-activity 실패 시 빈 lane 복구.
  - UI/UX 동작 변경 없음. 장애 원인 관측성만 보강.
- 단위/가드:
  - `py_compile`: pass
  - `tests.test_timeline_render_cache tests.test_editor_rendering_ownership_audit`: `40 tests OK`
  - `tools/check_maintenance_budget.py --json`: `ok=true`
  - `tools/qa_suite_runner.py quick`: pass
  - `git diff --check`: pass
- 분류:
  - 실패 없음.
  - code regression/fixture drift/environment-bundle issue 없음.

## 2D 플레이헤드 잔상 방지 repaint 가드 - 2026-05-21 11:20

- 실행 모드: Targeted
- 결과:
  - 단위/가드: pass
- 코드 반영:
  - `tools/audit_editor_rendering_ownership.py`에 `TimelineSingleOwnerPlayheadInvalidation` inventory를 추가했다.
  - single-owner 2D 경로에서 playhead, shadow playhead, drag-shadow playhead, dirty update가 full canvas repaint를 유지하는지 검사한다.
  - UI/UX 동작 변경 없음. 잔상 방지를 위해 이미 적용된 repaint 정책이 부분 repaint 최적화로 되돌아가지 않게 막는 회귀 가드다.
- 단위/가드:
  - `py_compile`: pass
  - `tools/audit_editor_rendering_ownership.py --json`: `ok=true`
  - `tests.test_editor_rendering_ownership_audit tests.test_timeline_render_cache`: `38 tests OK`
- 분류:
  - 실패 없음.
  - code regression/fixture drift/environment-bundle issue 없음.

## 2D 렌더링 ownership inventory 가드 확장 - 2026-05-21 11:16

- 실행 모드: Quick
- 결과:
  - Quick: pass, `output/manual_verification/latest/qa_suite_quick_20260521_111623`
- 코드 반영:
  - `tools/audit_editor_rendering_ownership.py`가 자막 텍스트 QML overlay, video control bar QML, video subtitle QML, timeline scenegraph layer까지 explicit diagnostic/scenegraph gate 뒤에 있는지 확인한다.
  - timeline paint 순서가 subtitle score, cut diamond, shadow/drag-shadow playhead, final playhead handle 순으로 유지되는지 검사한다.
  - UI/UX 동작 변경 없음. QML/SceneGraph 재유입을 잡는 정적 가드만 확장.
- 단위/가드:
  - `py_compile`: pass
  - `tools/audit_editor_rendering_ownership.py --json`: `ok=true`
  - `tests.test_editor_rendering_ownership_audit`: `2 tests OK`
- 분류:
  - 실패 없음.
  - code regression/fixture drift/environment-bundle issue 없음.

## automation-4 검토 항목 회수 및 full 재검증 - 2026-05-21 11:02~11:08

- 실행 모드: Major / Full
- 결과:
  - Major: pass, `output/manual_verification/latest/qa_suite_major_20260521_110523`
  - Full: pass, `output/manual_verification/latest/qa_suite_full_20260521_110628`
- 최종 `full` scenario:
  - `editor_compact_macau`: pass
  - `video_menu_macau`: pass
  - `save_export_macau`: pass
  - `menu_stt_lora_macau`: pass
  - `tinyping_fast_60s`: pass (`total_elapsed_sec=22.229`, `pipeline_elapsed_sec=9.843`, `peak_rss_bytes=431652864`, `final/raw=18/15`)
  - `tinyping_auto_60s`: pass (`total_elapsed_sec=43.163`, `pipeline_elapsed_sec=10.523`, `peak_rss_bytes=761839616`, `final/raw=18/15`)
  - `tinyping_high_60s`: pass (`total_elapsed_sec=25.561`, `pipeline_elapsed_sec=25.465`, `peak_rss_bytes=813219840`, `final/raw=16/16`)
- 실패 원인 분류 및 조치:
  - code regression: smart split 자동화가 playhead가 tiny fragment 또는 segment 밖에 있을 때 `smart_split_unavailable`로 오판하던 문제를 nearest splittable segment fallback으로 수정.
  - code regression: status/guided-subtitle-status가 UDP 제한 또는 send failure에서 `app_unreachable`로 보이던 문제를 compact/minimal fallback 응답으로 수정.
  - fixture/precondition drift: diamond 자동화가 compact 상태에서 stale line/right side를 고정해 `diamond_pair_missing`으로 실패하던 문제를 runner의 `closest` fallback으로 분리.
  - fixture/verification drift: snapshot/export command가 ok를 반환해도 산출물이 비어 있으면 실패로 기록하도록 `remote_verify.py`를 보강.
- 코드 수정 여부: 있음.
  - app command server UDP 응답 압축/최소 응답, status fallback cached resource 사용, editor smart split fallback, QA runner diamond fallback, remote verify artifact 검사.
- 문서 반영 여부: 있음.
  - `idea_item.md`, `test_result.md`, `lesson_n_learned.md` 반영.
- 남은 위험:
  - automation-4 전용 legacy coverage artifact는 과거 실패 기록이므로, 현재 기준 판정은 공식 `major/full` 통과 artifact를 기준으로 한다.
  - 멀티클립 long-running 상태 수렴은 이번 공식 suite 범위 밖이며, 이후 전용 반복 검증으로 분리한다.

## idea_item 최종 실행 QA 가드 보강 및 full 재검증 - 2026-05-21 10:12~10:26

- 실행 모드: Major / Full
- 결과:
  - Major: pass, `output/manual_verification/latest/qa_suite_major_20260521_102240`
  - Full: pass, `output/manual_verification/latest/qa_suite_full_20260521_102341`
- 최종 `full` scenario:
  - `editor_compact_macau`: pass
  - `video_menu_macau`: pass
  - `save_export_macau`: pass
  - `menu_stt_lora_macau`: pass
  - `tinyping_fast_60s`: pass (`total_elapsed_sec=22.553`, `pipeline_elapsed_sec=9.860`, `peak_rss_bytes=436256768`, `final/raw=18/15`)
  - `tinyping_auto_60s`: pass (`total_elapsed_sec=46.169`, `pipeline_elapsed_sec=10.230`, `peak_rss_bytes=783925248`, `final/raw=18/15`)
  - `tinyping_high_60s`: pass (`total_elapsed_sec=26.364`, `pipeline_elapsed_sec=26.262`, `peak_rss_bytes=1575256064`, `final/raw=16/16`)
- 실패 원인 분류 및 조치:
  - code regression: `verify_full_media_pipeline.py`가 spoken slice에서 `raw/final=0/0`이어도 pass로 집계할 수 있는 문제를 수정. 이후 non-trivial spoken slice는 자막 0개면 `empty_subtitle_output:*`로 실패한다.
  - environment-bundle issue: stale bundled Python process(`dist/macos/AI Subtitle Studio.app/Contents/Resources/app/main.py`)를 runner가 기존 앱으로 인식하지 못하던 문제를 수정. zombie/종료 중 PID는 restart blocker로 보지 않는다.
  - code regression: editor automation 중 layout/media refresh가 inline edit focus를 훔치면 `set_inline_cursor`/`commit_inline_edit`가 실패하던 문제를 마지막 smart-split request 복구로 수정.
- 코드 수정 여부: 있음.
  - QA verdict hardening, app bundle process restart detection, editor inline automation restore.
- 문서 반영 여부: 있음.
  - `test_case.md`, `README.md`, `idea_item.md`, `lesson_n_learned.md`, `waste_action_item.md`에 QA/렌더링/폐기 기준 반영.
- 남은 위험:
  - `automation4_full_ux_20260521_101007`의 추가 커버리지 항목은 이후 `qa_suite_major_20260521_110523` / `qa_suite_full_20260521_110628`에서 공식 suite 기준으로 회수했다.
  - aggressive quarter-overlap STT/LLM은 품질 barrier 전까지 default로 켜지지 않았다.

## automation-4 전체 UX + 팝업/메뉴/화면저장 보강 실행 - 2026-05-21 10:07~10:11

- 실행 모드: full 기준 커버리지를 유지한 상태에서 팝업/메뉴/화면저장 의무 화면을 모두 통합 수집.
- 실행 대상:
  - 실행 폴더 1: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/qa_suite_full_20260521_100216`
  - 실행 폴더 2: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/automation4_full_ux_20260521_101007`
- 결과 분류:
  - O: 43
  - X: 0
  - 검토필요: 14
- 검토필요 목록(우선순위별):
  - editor-begin-smart-split (`smart_split_unavailable`)
  - editor-set-inline-cursor (`inline_edit_inactive`)
  - editor-commit-inline-edit (`inline_edit_inactive`)
  - editor-move-diamond (`segment_not_found`)
  - editor-merge-diamond (`segment_not_found`)
  - export-subtitle-video (`command_timeout`)
  - stt-enable (`command_timeout`)
  - stt-disable (`command_timeout`)
  - lora-run-now (`command_timeout`)
  - lora-pause (`command_timeout`)
  - lora-resume (`command_timeout`)
  - start-multiclip (`command_timeout`)
  - open-home-before-multiclip (`app_unreachable`)
  - snapshot-after_save_export (`app_unreachable`)
  - snapshot-final_home (`app_unreachable`)
- 비고: 본 run은 `command_timeout`과 `app_unreachable`를 기능 실패와 분리해 추적하고, 아래 `idea_item`에 분류별 조치 요청으로 등록.
- 산출물:
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/automation4_full_ux_20260521_101007/coverage_summary.json`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/automation4_full_ux_20260521_101007/coverage_steps.jsonl`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/automation4_full_ux_20260521_101007/*.png`

### 화면 저장 의무 항목(실행 보강)

- 저장된 핵심 화면:
  - `home.png`
  - `editor_after_open_project.png`
  - `editor_after_open_srt.png`
  - `editor_segment.png`
  - `roughcut_after_start.png`
  - `playback_play.png`
  - `playback_pause.png`
  - `settings_dialog.png`
  - `speaker_dialog.png`
  - `dictionary_capture2.png`
  - `dictionary_dialog.png`
  - `final_home.png`
  - `final_editor.png`
  - `video_hidden.png`
  - `video_shown.png`
- 미생성 또는 무효(0B) 화면이 확인되면 우선 `검토필요`에서 분리.

## automation-4 full + 화면 저장 커버리지 실행 - 2026-05-21 10:02~10:06

- 실행 모드: full + 보완 커버리지
- 실행 대상 fixture:
  - 타이니핑 60초 기준 full: `tools/qa_suite_runner.py full`
  - 화면 저장/메뉴/러프컷 보강: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/automation4_coverage_run`
- 결과 분류:
  - O: `editor_compact_macau`, `video_menu_macau`, `save_export_macau`, `menu_stt_lora_macau`, `tinyping_fast_60s`, `tinyping_auto_60s`, `tinyping_high_60s`
  - X: 없음
  - 검토필요: `editor-move-diamond`, `editor-merge-diamond`, `start-multiclip-fast`, `wait-multiclip-done`, `export-subtitle-video`, `snapshot-after_save_export`, `snapshot-final_home`, `snapshot-final_editor`
- 핵심 산출물:
  - `output/manual_verification/latest/qa_suite_full_20260521_100216` (full pass: passed 7/7)
  - `output/manual_verification/latest/automation4_coverage_run/coverage_summary.json`
  - `output/manual_verification/latest/automation4_coverage_run/*.png`
- 안되는 항목 분류:
  - 기능 동작/상태 분리 필요: `editor-move-diamond`, `editor-merge-diamond`, `export-subtitle-video`
  - 통신/타임아웃 의심: `start-multiclip-fast`, `wait-multiclip-done`, `snapshot-after_save_export`, `snapshot-final_home`, `snapshot-final_editor`
- 검토 요청:
  - 위 8개 항목은 `idea_item.md`에 검토 요청 항목으로 등록했다.

### 참고

- 자동으로 저장된 메뉴/상태 화면:
  - `automation4_coverage_run/home.png`
  - `automation4_coverage_run/editor_after_open_project.png`
  - `automation4_coverage_run/editor_after_open_srt.png`
  - `automation4_coverage_run/editor_segment.png`
  - `automation4_coverage_run/settings_capture.png`
  - `automation4_coverage_run/speaker_capture.png`
  - `automation4_coverage_run/dictionary_capture.png`
  - `automation4_coverage_run/dictionary_capture2.png`
  - `automation4_coverage_run/playback_play.png`
  - `automation4_coverage_run/playback_pause.png`
  - `automation4_coverage_run/roughcut_after_start.png`
  - `automation4_coverage_run/video_hidden.png`
  - `automation4_coverage_run/video_shown.png`

## idea_item 최종 full QA 및 렌더링 inventory 가드 - 2026-05-21 09:52

- 브랜치: `opt/one-shot-quality-speed-20260521-0228`
- 코드 반영:
  - `tools/audit_editor_rendering_ownership.py` coverage를 segment text painter, cut diamond, shadow playhead, STT preview lane plan, waveform data source, timeline input hit target까지 확장.
  - 동작/UI 레이아웃 변경 없음. 기존 Qt Widgets/QPainter 2D 기본값을 벗어나는 회귀를 잡는 가드만 추가.
- 단위/가드:
  - `py_compile`: pass
  - `tools/audit_editor_rendering_ownership.py --json`: `ok=true`
  - `tests.test_editor_rendering_ownership_audit`: `2 tests OK`
- 공식 QA:
  - `tools/qa_suite_runner.py full`: pass, `output/manual_verification/latest/qa_suite_full_20260521_095045`
- `full` scenario 요약:
  - `editor_compact_macau`: pass
  - `video_menu_macau`: pass
  - `save_export_macau`: pass
  - `menu_stt_lora_macau`: pass
  - `tinyping_fast_60s`: pass (`total_elapsed_sec=22.291`, `pipeline_elapsed_sec=9.875`, `final/raw=18/15`)
  - `tinyping_auto_60s`: pass (`total_elapsed_sec=44.681`, `pipeline_elapsed_sec=9.908`, `final/raw=18/15`)
  - `tinyping_high_60s`: pass (`total_elapsed_sec=18.856`, `pipeline_elapsed_sec=18.763`, `final/raw=16/16`)
- 분류:
  - 실패 없음.
  - code regression/fixture drift/environment-bundle issue 없음.

## idea_item Phase 5.5 2D UI 렌더링 기본값 보정 - 2026-05-21 09:42

- 브랜치: `opt/one-shot-quality-speed-20260521-0228`
- 코드 반영:
  - `ui.gpu_rendering`에서 QML/SceneGraph UI를 기본 off로 고정하고, explicit env 또는 scenegraph opt-in setting이 있을 때만 허용.
  - timeline project vector metadata를 `timeline-qwidget-2d`로 정리.
  - runtime optimization profile과 default/custom settings의 editor backend를 `qwidget_2d` / OpenGL off / SceneGraph off로 정리.
  - `README.md`, `test_case.md`에 qwidget-2d 렌더링 ownership audit 경로를 반영.
- 단위/가드:
  - `py_compile`: pass
  - `tests.test_gpu_rendering`, `tests.test_project_context`, `tests.test_timeline_render_cache`: pass
  - `tools/audit_editor_rendering_ownership.py --json`: pass
  - `tests.test_editor_rendering_ownership_audit`: pass
  - `tests.test_runtime_optimization_profile`, `tests.test_native_macos_acceleration`: pass
  - `tools/check_maintenance_budget.py --json`: `ok=true`
  - `tools/qa_suite_runner.py quick`: pass, `output/manual_verification/latest/qa_suite_quick_20260521_094413`
- 분류:
  - UI/UX 재디자인 없음. macOS 합성 안정화를 위해 렌더링 backend 기본값만 Qt Widgets/QPainter 2D로 고정.

## idea_item Phase 5 native policy parity 보정 - 2026-05-21 09:30

- 브랜치: `opt/one-shot-quality-speed-20260521-0228`
- 코드 반영:
  - `tools/benchmark_native_policy_engine.py`가 Swift policy experimental gate를 켠 상태로 native helper를 측정하도록 수정.
  - LoRA native scoring 동점 정렬을 `retrieval_score -> quality -> docIndex`로 고정해 Python 상위 순서와 맞춤.
  - benchmark main 함수를 유지보수 가드 기준에 맞게 분리.
- 단위/가드:
  - `py_compile`: pass
  - `tests.test_native_policy_engine`: `7 tests OK`
  - `tools/check_maintenance_budget.py --json`: `ok=true`
  - `swift test` (`native/macos/AIStudioNative`): `38 tests`, pass
  - `tools/qa_suite_runner.py quick`: pass, `output/manual_verification/latest/qa_suite_quick_20260521_093458`
- 실제 벤치/판정:
  - artifact: `output/manual_verification/latest/idea_full_execute_20260521-0821/native_policy_parity_20260521_0930.json`
  - corrected Swift/native policy mini benchmark: LLM/deep/batch/LoRA top5 parity pass
  - speedup: `llm=0.308`, `deep=0.277`, `llm_batch=0.404`, `deep_batch=0.325`, `lora=0.382`
  - adoption: `python_small_batch_preferred`, `python_batch_preferred`, `python_for_this_index_size`
- 분류:
  - native policy helper default 승격은 parity가 아니라 speed regression으로 계속 blocked.

## idea_item Phase 4/5/8 품질 게이트 보강 - 2026-05-21 08:46~08:52

- 브랜치: `opt/one-shot-quality-speed-20260521-0228`
- 코드 반영:
  - subtitle benchmark quality gate를 `core.optimization.quality_gate.subtitle_quality_gate()`로 추가.
  - `tools/apply_subtitle_benchmark_quality_gate.py`를 추가해 기존 `benchmark_results.json`에 품질 보존 gate를 사후 적용.
  - Swift/native policy benchmark가 parity 실패 후보를 `native`로 표시하지 않도록 `blocked_quality_mismatch` 판정을 추가.
- 단위/가드:
  - `py_compile`: pass
  - `tests.test_runtime_optimization_profile`, `tests.test_benchmark_mode_profiles`: `35 tests OK`
  - `tests.test_native_policy_engine.NativePolicyBenchmarkReportTests`: pass
  - `tools/check_maintenance_budget.py --json`: `ok=true`
  - `swift test` (`native/macos/AIStudioNative`): `38 tests`, pass
  - `tools/qa_suite_runner.py quick`: pass, `output/manual_verification/latest/qa_suite_quick_20260521_085737`
  - `tools/qa_suite_runner.py major`: pass, `output/manual_verification/latest/qa_suite_major_20260521_085853`
  - `tools/qa_suite_runner.py full`: pass, `output/manual_verification/latest/qa_suite_full_20260521_085937`
- `full` scenario 요약:
  - `editor_compact_macau`: pass
  - `video_menu_macau`: pass
  - `save_export_macau`: pass
  - `menu_stt_lora_macau`: pass
  - `tinyping_fast_60s`: pass (`total_elapsed_sec=22.659`, `pipeline_elapsed_sec=10.020`, `final/raw=18/15`)
  - `tinyping_auto_60s`: pass (`total_elapsed_sec=47.412`, `pipeline_elapsed_sec=10.206`, `final/raw=18/15`)
  - `tinyping_high_60s`: pass (`total_elapsed_sec=27.063`, `pipeline_elapsed_sec=26.965`, `final/raw=16/16`)
- 실제 벤치/판정:
  - X5 STT full-parallel 재검증: `.codex_work/benchmarks/subtitle_pipeline_variants/20260521_084657/benchmark_results.json`
  - 품질 gate 산출물: `.codex_work/benchmarks/subtitle_pipeline_variants/20260521_084657/benchmark_quality_gate.md`
  - 기준 후보: `phase1_serial_selective_stt2`, `28.846s`, quality `72.986`, final `24`
  - full-parallel 후보: `10.169~10.451s`로 빠르지만 quality `71.563`, final `17`, gate fail
  - fail 사유: `quality_score_drop`, `readability_score_drop`, `cer_regression`, `timing_mae_regression`, `segment_retention_drop`
  - Macau fast 10회 반복: `output/manual_verification/latest/idea_full_execute_20260521-0821/macau_fast_repeat10_quality_gate/repeat_summary.json`
  - Macau fast pipeline avg/min/max: `7.628s / 7.516s / 7.854s`, final segments `5/5/5`
  - X5 modes 10회 반복: `output/manual_verification/latest/idea_full_execute_20260521-0821/x5_modes_repeat10_quality_gate/repeat_summary.md`
  - `mode_fast`: avg/min/max `10.373s / 10.024s / 11.046s`, quality `71.514`, final `17`, gate pass `0/10`
  - `mode_high_piecewise_drift`: avg/min/max `47.811s / 44.197s / 54.221s`, quality `72.989`, final `24`, gate pass `10/10`
  - Swift/native policy mini benchmark: helper speedup은 컸지만 `quality_check`가 모두 false라 adoption은 `blocked_quality_mismatch`
- 분류:
  - full-parallel STT default 승격은 quality regression으로 폐기 유지.
  - native policy helper default 승격은 parity mismatch로 blocked.

## idea_item Phase 2/3/5.5 실행 배치 - 2026-05-21 08:21~08:31

- 브랜치: `opt/one-shot-quality-speed-20260521-0228`
- 코드 반영:
  - STT/LLM memory pressure 판단을 `StageOwnedResourcePolicy`로 통합.
  - critical memory에서 STT collect worker 재사용, STT warm worker, LLM residency를 같은 정책으로 정리.
  - Apple M cut-boundary quarter prescan metadata/plan flag 추가.
  - 타임라인 인라인 자막 편집기를 opaque `QWidget` 파일로 분리해 macOS 합성 잔상/겹침 위험을 줄임.
- 단위/가드:
  - `py_compile`: pass
  - `tools/check_maintenance_budget.py --json`: `ok=true`
  - targeted unit: `248 tests OK`
  - `git diff --check`: pass
- 공식 QA:
  - `quick`: pass, `output/manual_verification/latest/qa_suite_quick_20260521_082403`
  - `major`: pass, `output/manual_verification/latest/qa_suite_major_20260521_082424`
  - `full`: pass, `output/manual_verification/latest/qa_suite_full_20260521_082856`
- `full` scenario 요약:
  - `editor_compact_macau`: pass
  - `video_menu_macau`: pass
  - `save_export_macau`: pass
  - `menu_stt_lora_macau`: pass
  - `tinyping_fast_60s`: pass (`total_elapsed_sec=22.326`, `pipeline_elapsed_sec=9.804`, `final/raw=18/15`)
  - `tinyping_auto_60s`: pass (`total_elapsed_sec=44.152`, `pipeline_elapsed_sec=9.833`, `final/raw=18/15`)
  - `tinyping_high_60s`: pass (`total_elapsed_sec=19.526`, `pipeline_elapsed_sec=19.431`, `final/raw=16/16`)
- 실제 미디어 벤치:
  - Macau fast: `total_elapsed_sec=8.064`, `pipeline_elapsed_sec=7.556`, `final/raw=5/3`, `stage_trim_total_failure_count=0`
  - X5 60s modes artifact: `.codex_work/benchmarks/subtitle_pipeline_variants/20260521_082610/benchmark_results.md`
  - X5 품질 1위: `mode_high_piecewise_drift`, `40.920s`, quality `72.989`, readability `94.568`
  - X5 속도/품질 균형 후보: `mode_fast`, `9.809s`, quality `71.514`, readability `93.057`
  - X5 STT1/STT2 full-parallel narrow benchmark: `.codex_work/benchmarks/subtitle_pipeline_variants/20260521_083704/benchmark_results.md`
  - full-parallel STT 판정: `10.387~10.625s`로 빠르지만 quality `71.563`, final segment `17`로 selective quality `72.986`, final segment `24`보다 낮아 기본 승격 폐기
- 분류:
  - 최종 실패 없음.
  - 최초 `quick`의 `app_bootstrap_failed`는 stale live app duplicate launcher로 인한 environment issue였고, stale process 종료 후 재실행 pass.
- 산출물:
  - `output/manual_verification/latest/idea_full_execute_20260521-0821/summary.md`

## v04.00.12 릴리즈 후보 full QA - 2026-05-21 02:23~02:25

- 사전 조치:
  - `./packaging/macos/build_app_bundle.sh`
  - 현재 코드/명령 surface가 반영된 `dist/macos/AI Subtitle Studio.app`로 stale bundle 가능성을 제거했다.
- 실행:
  - `./venv/bin/python tools/qa_suite_runner.py full`
- 결과:
  - `profile=full`
  - `scenario_count=7`
  - `failed_count=0`
- 산출물:
  - `output/manual_verification/latest/qa_suite_full_20260521_022256`
  - `output/manual_verification/latest/qa_suite_full_20260521_022256/suite_result.json`
- scenario 요약:
  - `editor_compact_macau`: pass
  - `video_menu_macau`: pass
  - `save_export_macau`: pass
  - `menu_stt_lora_macau`: pass
  - `tinyping_fast_60s`: pass (`total_elapsed_sec=26.031`, `peak_rss_bytes=440418304`)
  - `tinyping_auto_60s`: pass (`total_elapsed_sec=44.917`, `peak_rss_bytes=918962176`)
  - `tinyping_high_60s`: pass (`total_elapsed_sec=19.358`, `peak_rss_bytes=1294532608`)
- 분류:
  - 실패 없음
  - 집계 문제/fixture drift/environment bundle issue 없음

실행 일시: 2026-05-20 10:04:47 ~ 10:08:00 (KST)
대상 모드: full
실행 폴더: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full`

## 5개 액션아이템 집중 재실행 - 2026-05-20 12:01~12:12

- 실행 폴더: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_120128_automation4_action_items_rerun`
- 이번 재실행은 23~27번 액션아이템만 대상으로 수행했다.
- 판정:
  - 검토필요
    - 23) 멀티클립 파이프라인: `start-multiclip` 응답은 `app_unreachable/timed out`였지만, 앱 내부 로그에서는 `전체 5/5개 클립 처리 완료`까지 진행됨. 기능 완료와 automation 응답 불안정이 분리되어 추가 검토 필요.
    - 25) 재생 제어/비디오 메뉴: `editor-playback play/pause`는 fresh app에서 모두 `ok=true`로 통과했으나 video 메뉴 자동화 커맨드는 여전히 없음.
  - X
    - 24) 세그먼트 편집 시퀀스: `set-playhead`, `select-segment`, `move-segment-left/right`, `move-diamond`, `merge-diamond`는 통과했지만 `begin-smart-split=smart_split_unavailable`, `set-inline-cursor/commit-inline-edit=inline_edit_inactive`로 full pass 실패.
    - 26) 저장/내보내기: `save-project`는 통과했지만 자막 저장/자막 출력/자막 영상 출력 산출물 검증은 아직 자동화되지 않음.
    - 27) 메뉴/LoRA/화자/STT: settings/speaker/dictionary popup 캡처와 STT on/off는 통과했지만 `personalization-idle run-now/pause/resume`는 CLI 기준 타임아웃. 다만 앱 로그상 `LoRA 학습 시작`은 실제로 발생.
- 통과한 세부 확인:
  - 에디터 직접 명령: `open-project`, `capture-snapshot`, `editor-set-playhead`, `editor-select-segment`, `editor-move-segment-left/right`, `editor-move-diamond`, `editor-merge-diamond`, `save-project`
  - 팝업 캡처: `settings_dialog.png`, `speaker_dialog.png`, `dictionary_dialog.png`
  - STT 토글: `enabled=false -> true -> false`, state=`ready_to_listen -> disabled`
- 핵심 근거:
  - 에디터 직접 실행 결과: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_120128_automation4_action_items_rerun/command_status_direct.tsv`
  - 멀티클립/초기 배치 결과: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_120128_automation4_action_items_rerun/command_status.tsv`
  - STT 상태: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_120128_automation4_action_items_rerun/menu/status_stt_enabled.json`, `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_120128_automation4_action_items_rerun/menu/status_stt_disabled.json`
  - UI 화면: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_120128_automation4_action_items_rerun/editor_direct/*.png`, `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_120128_automation4_action_items_rerun/menu/*.png`

> 아래 `시나리오별 판정` 본문은 10:04 full pass 기준이고, 위 집중 재실행 결과가 23~27번 액션아이템 관련 최신 판정이다.

## item 1,2 보강 후 마카오 기능테스트 - 2026-05-20 12:50~12:52

- 실행 폴더:
  - 1차: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_125036_automation4_item12_macau_function`
  - 2차(최종): `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_125219_automation4_item12_macau_function_retry`
- 코드 반영:
  - `personalization-idle run-now/pause/resume`를 long-running action 기준 `accepted + queued` 비동기 응답으로 변경.
  - `editor-begin-smart-split`는 요청 line이 현재 playhead 구간과 맞지 않으면 playhead가 걸린 세그먼트로 fallback하도록 보강.
  - `smart_split_unavailable`, `inline_edit_inactive` 실패 시 `editor_runtime` snapshot을 함께 반환하도록 보강.
- 마카오 기능테스트 결과:
  - `open-project`: `ok=true`
  - `editor-set-playhead --center 1.5`: `ok=true`
  - `editor-begin-smart-split --line 0`: `ok=true`
    - 의미: line 0 요청이었지만 playhead 기준 fallback으로 split 진입 성공
  - `editor-set-inline-cursor 2`: `ok=true`
  - `editor-commit-inline-edit`: `ok=true`
  - `save-project`: `ok=true`
  - `personalization-idle run-now`: `ok=true`, `accepted=true`, `queued=true`
  - `personalization-idle pause`: `ok=true`, `accepted=true`, `queued=true`
  - `personalization-idle resume`: `ok=true`, `accepted=true`, `queued=true`
- 핵심 근거:
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_125219_automation4_item12_macau_function_retry/command_status.tsv`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_125219_automation4_item12_macau_function_retry/logs/personalization_run_now.stdout`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_125219_automation4_item12_macau_function_retry/logs/personalization_pause.stdout`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_125219_automation4_item12_macau_function_retry/logs/personalization_resume.stdout`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_125219_automation4_item12_macau_function_retry/status_after_split.json`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_125219_automation4_item12_macau_function_retry/snapshots/after_split.png`
- 이번 테스트 기준 판단:
  - 24) 세그먼트 편집 시퀀스: targeted Macau path는 통과
  - 27) LoRA run/pause/resume command ack: 통과
  - 남은 이슈:
    - 23) 멀티클립 ack/status 분리
    - 25) 비디오 메뉴 자동화 surface 부재
    - 26) 자막 저장/자막 출력/자막 영상 출력 산출물 검증 미구현
    - personalization 이후 최종 `status`는 `status_snapshot_fallback`가 남아 있어 별도 상태 surface 보강 필요

## 다음 실행 - 멀티클립 ack/status 재검증 - 2026-05-20 13:13

- 실행 폴더: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_131332_automation4_multiclip_ack_macau`
- 수정:
  - `start-multiclip`에서 editor wait/auto-start 동기 대기를 제거하고 즉시 `accepted=true`, `queued=true` 응답으로 변경.
- 마카오 5클립 결과:
  - `start-multiclip`: `ok=true`, `accepted=true`, `queued=true`
  - 응답 본문에 즉시 `queue_runtime` 포함:
    - `row_count=5`
    - `done_rows=0`
    - `all_done=false`
  - `status` 1회차: `row_count=5`, `done_rows=0`, `all_done=false`
  - `status` 2회차: `row_count=5`, `done_rows=5`, `error_rows=0`, `all_done=true`
  - `status_snapshot_fallback`: 관측되지 않음
- 판정:
  - 23) 멀티클립 파이프라인 시나리오의 앱 타임아웃/대기 상태 해소: O
- 근거 파일:
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_131332_automation4_multiclip_ack_macau/logs/start_multiclip.stdout`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_131332_automation4_multiclip_ack_macau/poll_summary.tsv`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_131332_automation4_multiclip_ack_macau/result.txt`

## 다음 실행 - 비디오 메뉴 마카오 검증 - 2026-05-20 13:37

- 실행 폴더: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_133752_automation4_video_menu_macau`
- 수정:
  - `editor-video show/hide/toggle` command 추가
  - status/editor_runtime에 `video_visible`, `active_footer_menu_id` 노출
- 마카오 프로젝트 결과:
  - `editor-playback play`: `ok=true`
  - `editor-playback pause`: `ok=true`
  - `editor-video hide`: `ok=true`, `video_visible=false`
  - `editor-video show`: `ok=true`, `video_visible=true`
  - hide/show 후 각각 snapshot 저장 성공
- 판정:
  - 25) 재생 제어 + 비디오 메뉴: O
- 근거 파일:
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_133752_automation4_video_menu_macau/logs/video_hide.stdout`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_133752_automation4_video_menu_macau/status_after_video_hide.json`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_133752_automation4_video_menu_macau/logs/video_show.stdout`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_133752_automation4_video_menu_macau/status_after_video_show.json`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_133752_automation4_video_menu_macau/snapshots/video_hidden.png`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_133752_automation4_video_menu_macau/snapshots/video_shown.png`

## 다음 실행 - 저장/출력 마카오 검증 - 2026-05-20 13:46~13:49

- 실행 폴더:
  - 1차: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_134731_automation4_save_export_macau`
  - 2차(최종): `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_134922_automation4_save_export_macau_retry`
- 수정:
  - `save-subtitles`, `export-subtitles`, `export-subtitle-video` command 추가
  - `save-subtitles`/`export-subtitle-video`는 `변경사항이 없습니다` 경로에서도 `_preferred_single_srt_output_path` 또는 `get_srt_path(media_path)` 기준으로 기존 SRT를 역추론하도록 fallback 보강
- 1차 재실행:
  - stale app process 때문에 세 command가 `unknown_command`로 실패
  - 앱 재기동 후 동일 시나리오 재실행
- 마카오 retry 결과:
  - `save-project`: `ok=true`
    - 프로젝트 파일: `178922 bytes -> 179394 bytes`, mtime 갱신
  - `save-subtitles`: `ok=true`
    - 저장 자막: `/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217224203_0075_D.srt`, `2866 bytes`
  - `export-subtitles`: `ok=true`
    - 수동 export: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_134922_automation4_save_export_macau_retry/exports/DJI_20260217224203_0075_D_manual_export.srt`, `2866 bytes`
  - `export-subtitle-video`: `ok=true`
    - 자막영상: `/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217224203_0075_D_자막소스.mov`
    - 파일 변화: `3380968 bytes -> 3272377 bytes`, mtime 갱신
  - `capture-snapshot`: `ok=true`, snapshot 저장 성공
  - 최종 `status`: `status_snapshot_fallback` 관측되지 않음
- 판정:
  - 26) 저장/내보내기: O
- 근거 파일:
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_134922_automation4_save_export_macau_retry/command_status.tsv`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_134922_automation4_save_export_macau_retry/summary.json`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_134922_automation4_save_export_macau_retry/snapshots/after_save_export.png`

## 다음 실행 - 세그먼트 편집 full 1pass 마카오 검증 - 2026-05-20 16:11~16:16

- 실행 폴더:
  - 시도 1: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_161111_automation4_editor_fullpass_macau`
  - 시도 2: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_161221_automation4_editor_fullpass_macau_retry`
  - 시도 3: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_161348_automation4_editor_fullpass_macau_settled`
  - 최종: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_161630_automation4_editor_fullpass_macau_compact`
- 관찰:
  - `open-project` 직후 바로 `begin-smart-split`를 넣으면 `editor-set-playhead` 응답은 `playhead_sec=1.5015`, `smart_split_ready=true`인데도 실제 다음 명령에서 playhead가 `0.0`으로 되감기며 `smart_split_unavailable`가 발생했다.
  - `status`를 move 단계마다 과도하게 넣으면 `move_diamond` 이후 `app_unreachable/timed out`가 섞여 실제 편집 command 성공 여부를 흐렸다.
- 최종 시나리오:
  - `open-project` 후 2초 settle
  - `editor-set-playhead 1.5 --center` 후 1초 settle
  - `editor-begin-smart-split --at-playhead`
  - `editor-set-inline-cursor 2`
  - `editor-commit-inline-edit`
  - `editor-move-segment-left --line 1`
  - `editor-move-segment-right --line 1`
  - `editor-move-diamond --line 1 --side right`
  - `editor-merge-diamond --line 1 --side right`
  - `save-project`
- 최종 결과:
  - 위 13개 step이 전부 `ok=true`
  - 최종 `status`도 `ok=true`, `status_snapshot_fallback` 없음
- 판정:
  - 24) 세그먼트 편집 시퀀스: O
- 근거 파일:
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_161630_automation4_editor_fullpass_macau_compact/command_status.tsv`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_161630_automation4_editor_fullpass_macau_compact/summary.json`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_161630_automation4_editor_fullpass_macau_compact/snapshots/initial.png`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_161630_automation4_editor_fullpass_macau_compact/snapshots/final.png`

## 다음 실행 - 메뉴/LoRA/STT full 커버리지 마카오 검증 - 2026-05-20 16:22~16:23

- 실행 폴더:
  - 최종: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_162208_automation4_menu_stt_lora_macau_final`
- 시나리오:
  - `open-project`
  - `open-settings` → `capture-active-dialog` → `close-active-dialog`
  - `open-speaker-settings` → `capture-active-dialog` → `close-active-dialog`
  - `open-dictionary` → `capture-dictionary-snapshot`
  - `editor-stt-mode enable` → status
  - `editor-stt-mode disable` → status
  - `personalization-idle run-now` → status
  - `personalization-idle pause` → status
  - `personalization-idle resume` → status
  - 최종 status 및 3초 settle 후 status 추가 수집
- 결과:
  - 모든 command가 `ok=true`
  - popup 3종 PNG 저장 성공
  - STT 상태 전환 확인:
    - enabled: `false -> true -> false`
    - state: `disabled -> ready_to_listen -> disabled`
  - LoRA ack 확인:
    - `run-now`: `personalization_idle_run_now_accepted`
    - `pause`: `personalization_idle_pause_accepted`
    - `resume`: `personalization_idle_resume_accepted`
  - `pause/resume` 직후 status 2개는 `status_snapshot_fallback=true`였지만, 3초 settle 후 `/status/final_status_settled_3s.json`에서는 fallback 없이 안정화됨
- 판정:
  - 27) 메뉴/LoRA/STT 커버리지: O
- 근거 파일:
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_162208_automation4_menu_stt_lora_macau_final/command_status.tsv`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_162208_automation4_menu_stt_lora_macau_final/status/status_stt_enabled.json`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_162208_automation4_menu_stt_lora_macau_final/status/status_stt_disabled.json`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_162208_automation4_menu_stt_lora_macau_final/status/final_status_settled_3s.json`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_162208_automation4_menu_stt_lora_macau_final/menu/settings_dialog.png`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_162208_automation4_menu_stt_lora_macau_final/menu/speaker_dialog.png`
  - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_162208_automation4_menu_stt_lora_macau_final/menu/dictionary_dialog.png`

## 후속 묶음 실행 - 2026-05-20 11:19~11:25

- 수정: `tools/automation_command_client.py` 추가, `tools/appctl.py`/`tools/remote_verify.py`에서 순수 상태 조회(`status/ping/guided-subtitle-status`)만 준비 대기 재시도하도록 보강.
- 수정: `capture-snapshot`은 파일 저장을 큐에 넣는 명령이므로 재시도 대상에서 제외해 중복 스냅샷 요청을 막음.
- 마카오 자막 생성 smoke:
  - 경로: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_action_batch_automation_retry_macau/pipeline_fast/tinyping_full_verify.json`
  - 결과: `ok=true`, `pipeline_elapsed_sec=7.375`, `total_elapsed_sec=7.465`, `final_segment_count=5`, `raw_segment_count=3`, `peak_rss_bytes=261423104`
- 마카오 편집 자동화 command-only smoke:
  - 경로: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_action_batch_automation_retry_macau/editor_sequence_command_only/report.json`
  - 결과: `open-project`, `set-playhead`, 단일 `snapshot` 모두 `ok=true`; 최종 `editor_open=true`, `segment_count=5`, active text=`와인이 되게 많네`
  - 스냅샷: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_action_batch_automation_retry_macau/editor_sequence_command_only/snapshot.png`
- 재생 제어 smoke:
  - `editor-playback play`: `ok=true`, active segment=`와인이 되게 많네`
  - `editor-playback pause`: `ok=true`, pause 후 editor_runtime 응답 확인
- 남은 판정:
  - 멀티클립 all_done 수렴, full editor action sequence, 저장/내보내기, 메뉴/LoRA/STT 세부 커버리지는 아직 미완료.
  - `snapshot-each-step`은 정상 캡처 파일이 생성되더라도 명령 응답이 늦을 수 있어 full 시나리오에서는 단일 최종 스냅샷 또는 단계별 충분한 settle 정책으로 재설계 필요.

## 후속 묶음 실행 - 2026-05-20 11:38~11:42

- 수정: `tools/remote_verify.py`의 `--actions`에 `play`, `pause`, `save-project`를 추가하고 액션 매핑 helper로 분리해 유지보수 가드 한도를 지켰다.
- 테스트 추가: `tests/test_remote_verify_actions.py`
- 마카오 편집/저장/재생 시나리오:
  - 경로: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_action_batch_remote_actions_macau/editor_play_save/report.json`
  - 결과: `open-project`, `set-playhead`, `play`, `pause`, `save-project`, `snapshot` 모두 `ok=true`
  - 최종 상태: `editor_open=true`, `segment_count=5`, active text=`와인이 되게 많네`
  - 스냅샷: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_action_batch_remote_actions_macau/editor_play_save/snapshot.png`
- 마카오 자막 생성 smoke:
  - 경로: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_action_batch_remote_actions_macau/pipeline_fast/tinyping_full_verify.json`
  - 결과: `pipeline_elapsed_sec=6.899`, `total_elapsed_sec=6.990`, `final_segment_count=5`, `raw_segment_count=3`, `readability_score=100.0`, `peak_rss_bytes=260128768`
- 남은 판정:
  - 25번의 play/pause 응답은 안정화되었으나 video 메뉴 전환 커맨드는 아직 미구현.
  - 26번의 프로젝트 저장은 성공했으나 자막 파일 저장/자막 영상 출력 산출물 검증은 아직 미구현.

## 후속 묶음 실행 - 2026-05-20 16:14~16:16

- 수정:
  - `tools/remote_verify.py`의 `--actions`에 `video-show/hide/toggle`, `stt-enable/disable/toggle`, `open-dictionary`, `open-settings`, `open-speaker-settings`, `capture-active-dialog`, `capture-dictionary`, `close-active-dialog`, `lora-run-now/pause/resume`를 추가했다.
  - popup 캡처는 전체 창 snapshot과 분리된 step PNG 경로를 쓰도록 했다.
  - `tests/test_remote_verify_actions.py`에 신규 action 매핑 테스트를 추가했다.
- 마카오 full editor 1pass:
  - 경로: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_automation4_editor_fullpass_macau/report.json`
  - 결과: `open`, `set-playhead`, `select-segment`, `begin-smart-split`, `set-inline-cursor`, `commit-inline-edit`, `move-segment-left/right`, `move-diamond`, `merge-diamond`, `snapshot` 전 단계 `ok=true`
  - 최종 상태: `segment_count=56`, `active_line=1`, `inline_edit_active=false`
- 마카오 menu/STT/LoRA full pass:
  - 경로: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_automation4_menu_stt_lora_macau/report.json`
  - 결과: `open-dictionary`, `capture-dictionary`, `open-settings`, `capture-active-dialog`, `open-speaker-settings`, `capture-active-dialog`, `stt-enable`, `stt-disable`, `lora-run-now`, `lora-pause`, `lora-resume`, `snapshot` 전 단계 `ok=true`
  - 증거 PNG: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_automation4_menu_stt_lora_macau/capture-dictionary.png`, `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_automation4_menu_stt_lora_macau/capture-active-dialog.png`
- 판정:
  - 24) 세그먼트 편집 시퀀스: O
  - 27) 메뉴/LoRA/화자/STT: O

## 후속 묶음 실행 - 2026-05-20 16:28~16:33

- 수정:
  - `ui/main/app_command_bridge.py`의 대형 command 분기 블록을 `ui/main/app_command_bridge_handlers.py`로 분리했다.
  - 공개 API(`execute_app_command`, `dispatch_app_command`)와 status/nonfatal helper 표면은 유지했다.
- 가드/테스트:
  - `./venv/bin/python tools/check_maintenance_budget.py --json` → `issue_count=0`
  - `./venv/bin/python -m unittest tests.test_app_command_bridge tests.test_remote_verify_actions tests.test_automation_command_client -q` → `56 tests OK`
- 마카오 editor smoke:
  - 경로: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_maintenance_guard_split_macau_editor/report.json`
  - 결과: `open`, `set-playhead`, `select-segment`, `begin-smart-split`, `set-inline-cursor`, `commit-inline-edit`, `move-segment-left/right`, `move-diamond`, `merge-diamond`, `snapshot` 전 단계 `ok=true`
- 마카오 menu/STT/LoRA smoke:
  - 경로: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_maintenance_guard_split_macau_menu/report.json`
  - 결과: dictionary/settings/speaker popup capture, `stt-enable/disable`, `lora-run-now/pause/resume`, `snapshot` 전 단계 `ok=true`
  - 증거 PNG: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_maintenance_guard_split_macau_menu/capture-dictionary.png`, `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_maintenance_guard_split_macau_menu/capture-active-dialog.png`
- 마카오 fast pipeline smoke:
  - 경로: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_maintenance_guard_split_macau_pipeline_fast/tinyping_full_verify.json`
  - 결과: `pipeline_elapsed_sec=7.284`, `total_elapsed_sec=7.376`, `final_segment_count=5`, `raw_segment_count=3`, `peak_rss_bytes=265666560`
- 판정:
  - 11) `app_command_bridge.py` maintenance guard split: O

## 최상단 판정 (요청 형식: X / 검토필요 / O)

- X: 7개
  - 3) 멀티클립 열기 후 자막 생성 흐름
  - 5) 모든 메뉴 1회 확인 + LoRA 실행/종료
  - 7) 프로젝트/자막 저장, 자막 출력, 자막 영상 출력
  - 8) 자막 에디터 기능(단축기, 에디터 동작)
  - 9) 자막 세그먼트 에디터 + 팝업 메뉴 시나리오
  - 10) 편집 후 컷 경계/플레이헤드 동작 검증
  - 11) 지디오 재생 및 비디오 메뉴 동작
- 검토필요: 2개
  - 6) 시작/종료 테스트
  - 13) STT 모드 테스트
- O: 4개
  - 1) SRT 열기 + 에디터 진입
  - 2) 영상열기 후 자막 생성(티니핑 60초 fast/auto/high)
  - 4) 화면간 전환(홈 ↔ 에디터 기본 이동)
  - 12) 화자 관련 메뉴(단, 토글 동작은 추가 검증 필요)

> 사용자 요청대로 안 되거나 검토필요 항목을 최상단에 먼저 배치했습니다.

## 시나리오별 판정

1. 자막열기 후 자막 편집기능
   - 판정: X (편집 액션이 완성되지 않음)
   - 근거 파일:
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/open_srt/open_srt.png`
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/open_srt/report.md`

2. 영상열기 후 자막 생성 (fast / auto / high)
   - 판정: O (티니핑 60초 구간 실행 성공)
   - 근거 파일:
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/tinyping_60s_fast/fast_60s/tinyping_full_verify.md`
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/tinyping_60s_auto/auto_60s/tinyping_full_verify.md`
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/tinyping_60s_high/high_60s/tinyping_full_verify.md`
   - 비고: `full` 전체길이 아니라 요청한 smoke 기준(60초) 검증으로 수행.

3. 멀티클립 열기 후 자막 생성
   - 판정: X
   - 근거 파일:
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/start_multiclip_fast.json` (`ok=false`, `app_unreachable`, `timed out`)
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/status_after_multiclip_fast.json` (`queued=true`)
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/multiclip_fast/report.json` (메인 윈도우 큐 대기)
   - 화면 저장: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/multiclip_fast/multiclip_fast_after_start.png`

4. 화면간 전환 (홈, 에디터, 러프컷, 숏폼)
   - 판정: O (기본 이동은 확인)
   - 근거 파일:
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/show_home.json` (`home_visible`)
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/show_home_after.json`
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/home/report.md`
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/home_after/report.md`
   - 비고: 스크린샷이 1회성 홈/after 수준으로만 남아 있어 숏폼/러프컷 상세 화면은 검증 범위 확장 필요.

5. 모든 메뉴 1회 + LoRA 실행/종료
   - 판정: X
   - 근거 파일:
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/open_dictionary.json` (`dictionary_visible`)
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/dictionary/dictionary_overlay.png`
   - 비고: 메뉴 전체 순회와 LoRA start/stop은 실행 스크립트에 명시되지 않음.

6. 시작 / 종료 테스트
   - 판정: 검토필요
   - 근거 파일:
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/status_before.json` (`editor_state=ST_IDLE`, 앱 존재)
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/status_final.json` (종료 상태 후 확인 자료는 존재하나 종료 커맨드 로그 없음)

7. 프로젝트 저장, 자막 저장, 자막 출력, 자막 영상 출력
   - 판정: X
   - 근거 파일:
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/save_project_before_roughcut.json` (`ok=false`, `app_unreachable` / `timed out`)
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/roughcut/report.md` (자막 출력/러프컷 후처리 대기, 완료 상태 미달)
   - 비고: 저장/저장취소 상태만 보이고, 출력 산출물 경로 검증 미완료.

8. 자막에디터 기능 확인 (단축기, 에디터 기능)
   - 판정: X
   - 근거 파일:
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/editor_project_sequence/report.json` (`select-segment`~`merge-diamond` 일부 `ok=False`)
   - 저장 화면: `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/editor_project_sequence/initial.png` 외 8개 편집 시도 화면

9. 자막 세그먼트 에디터 (팝업메뉴, ux 시나리오 전부)
   - 판정: X
   - 근거 파일:
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/editor_project_sequence/report.json` (편집 단게 다수 실패)
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/test_case.md` (팝업/ux 항목 누락 분기 보강 대상)

10. 임의 편집 후 동작 확인 (플레이헤드 이동 후 컷 경계)
   - 판정: X
   - 근거 파일:
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/editor_project_sequence/report.md` (`set-playhead`은 성공했으나 이동/분할/병합 연계 실패)
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/status_after_playback.json` (`app_unreachable`)

11. 지디오 재생 확인, 비디오 메뉴 동작
   - 판정: X
   - 근거 파일:
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/playback_play.json` (`app_unreachable`, `timed out`)
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/playback_pause.json` (`app_unreachable`, `timed out`)

12. 화자 관련 메뉴 테스트
   - 판정: O (메뉴 진입 흔적 확인됨, 기능 동작은 미완)
   - 근거 파일:
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/status_after_multiclip_fast.json`
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/roughcut/report.md`

13. STT 모드 테스트
   - 판정: 검토필요
   - 근거 파일:
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/tinyping_60s_fast/fast_60s/tinyping_full_verify.md`
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/tinyping_60s_auto/auto_60s/tinyping_full_verify.md`
     - `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/tinyping_60s_high/high_60s/tinyping_full_verify.md`
   - 비고: fast/auto/high는 모드별 결과는 확인되었지만, STT 세부 모드 토글(예: STT1/STT2 선택 UI/메뉴) 커맨드 단에서 직접 검증되지 않음.

## 저장된 UI 화면

- `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/home/home.png`
- `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/home_after/home_after_tests.png`
- `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/open_srt/open_srt.png`
- `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/dictionary/dictionary_overlay.png`
- `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/roughcut/roughcut_after_start.png`
- `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/multiclip_fast/multiclip_fast_after_start.png`
- `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/macao_media/macao_media_loaded.png`
- `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/editor_project_sequence/*.png`
- `/Users/u_mo_c/Downloads/ai_subtitle_studio/output/manual_verification/latest/20260520_100447_automation4_full/pipeline/pipeline_started.png` (snapshot 큐 완료 지연)

## 조치 항목 반영

- `ACTION_ITEMS.md`에 검토 요청 항목을 추가했으므로 각 X/검토필요 항목은 해당 액션의 리뷰가 완료되어야 다음 full pass 가능.
## 후속 묶음 실행 - 2026-05-20 17:05~17:15

- 범위: Action item `10`, `18`
- 목적: subtitle generation memory trim 비용을 stage family별로 누적 계측하고, benchmark artifact에 바로 드러나게 만들기.

### 코드 변경

- `core/runtime/memory_trim_summary.py`
  - `subtitle_generation_latest.json`용 stage family rollup helper 추가.
- `core/runtime/memory_manager.py`
  - `stage_trim_summary`를 checkpoint snapshot에 기록.
  - chunk별 stage 이름을 family 기준으로 누적해 반복 벤치 비교가 가능하게 조정.
- `core/pipeline/subtitle_memory_guard.py`
  - memory guard stage emit/checkpoint 실패를 typed nonfatal log로 노출.
- `tools/verify_full_media_pipeline.py`
  - `summary_metrics` 공개 함수화.
  - `stage_trim_total_elapsed_ms`, `stage_trim_executed_count`, `stage_trim_slowest_stage`를 per-run/repeat artifact에 추가.

### 자동 검증

- `./venv/bin/python -m unittest tests.test_runtime_memory_manager tests.test_verify_full_media_pipeline -q`
  - 결과: `25 tests OK`
- `./venv/bin/python -m py_compile core/runtime/memory_trim_summary.py core/runtime/memory_manager.py core/pipeline/subtitle_memory_guard.py tools/verify_full_media_pipeline.py tests/test_runtime_memory_manager.py tests/test_verify_full_media_pipeline.py`
  - 결과: `OK`
- `./venv/bin/python tools/check_maintenance_budget.py --json`
  - 결과: `issue_count=0`
- `git diff --check -- core/runtime/memory_trim_summary.py core/runtime/memory_manager.py core/pipeline/subtitle_memory_guard.py tools/verify_full_media_pipeline.py tests/test_runtime_memory_manager.py tests/test_verify_full_media_pipeline.py`
  - 결과: `OK`

### 마카오 반복 벤치

- 명령:
  - `./venv/bin/python tools/verify_full_media_pipeline.py --media '/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217225132_0079_D.MP4' --mode fast --repeat 3 --output-dir output/manual_verification/latest/20260520_action_batch_trim_summary_macau_fast_repeat3`
- 결과:
  - run1 `pipeline_elapsed_sec=7.213`, `total_elapsed_sec=7.524`
  - run2 `pipeline_elapsed_sec=6.616`, `total_elapsed_sec=6.682`
  - run3 `pipeline_elapsed_sec=6.646`, `total_elapsed_sec=6.712`
  - 평균 `pipeline_elapsed_sec=6.825`
  - `final_segment_count=5` 고정, `raw_segment_count=3` 고정
  - 이번 반복은 `pressure_stage=normal`이라 `stage_trim_executed_count`, `stage_trim_total_elapsed_ms`는 비어 있었다.
- 산출물:
  - `output/manual_verification/latest/20260520_action_batch_trim_summary_macau_fast_repeat3/repeat_summary.json`
  - `output/manual_verification/latest/20260520_action_batch_trim_summary_macau_fast_repeat3/repeat_summary.csv`

## 후속 묶음 실행 - 2026-05-20 17:45~17:57

- 범위: Action item `16`, `18`
- 목적: 실앱 `guided-subtitle-run` 반복에서 `critical` 재현 여부, status timeout, trim 요약, worker residency를 같이 저장한다.

### 코드 변경

- `tools/debug_guided_subtitle_memory.py`
  - 실앱 `guided-subtitle-run` 반복 디버그 도구 추가
  - `guided-subtitle-status` timeout을 재시도로 흡수
  - status가 끝까지 막혀도 `guided_snapshots/*completed*.png`로 완료 판정
  - run별 `runtime_monitor`, `subtitle_generation_monitor`, `process_snapshot` 즉시/settle 후 저장
- `tests/test_debug_guided_subtitle_memory.py`
  - processing 판단, critical log 감지, completed snapshot 감지 테스트 추가

### 자동 검증

- `./venv/bin/python -m unittest tests.test_debug_guided_subtitle_memory -q`
  - 결과: `3 tests OK`
- `./venv/bin/python -m py_compile tools/debug_guided_subtitle_memory.py tests/test_debug_guided_subtitle_memory.py`
  - 결과: `OK`
- `./venv/bin/python tools/check_maintenance_budget.py --json`
  - 결과: `issue_count=0`

### 마카오 실앱 디버그

- live warm-session status 관찰:
  - `guided-subtitle-status` 응답에서 `runtime_resource.pressure_stage=critical`
  - recent stage logs에
    - `🧹 [STT2] 메모리 critical: STT persistent worker 재사용 중단`
    - `🧹 [STT1] 메모리 critical: STT persistent worker 재사용 중단`
  - 동일 응답에서 `stt_transcribe_chunk:1/1`, `stt_transcribe_done`, `subtitle_optimize_start`, `stt_optimizer_threads_done` 메모리 로그가 함께 보였다.
- partial artifact:
  - `output/manual_verification/latest/20260520_action_batch_guided_memory_macau_repeat3_v3/run_01/subtitle_generation_monitor_after.json`
  - 결과: `subtitle_generation_stage=stt_optimizer_threads_done`, `stage_trim_executed_count=1`, `stage_trim_total_elapsed_ms=14.669`
- fresh app 1회 검증:
  - 명령:
    - `./venv/bin/python tools/debug_guided_subtitle_memory.py --media '/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217225132_0079_D.MP4' --repeat 1 --timeout 8 --poll-sec 1.0 --done-stable-sec 2.0 --post-run-settle-sec 2.0 --output-dir output/manual_verification/latest/20260520_action_batch_guided_memory_macau_repeat1_v4`
  - 결과:
    - `elapsed_sec=21.247`
    - `completed_via_snapshot=true`
    - `runtime_pressure_after=normal`
    - `memory_pressure_after=normal`
    - `subtitle_stage_after=stt_optimizer_threads_done`
    - `process_total_after=4`, `process_total_after_settle=4`
    - `process_rss_after_bytes=889126912`
    - `process_rss_after_settle_bytes=87113728`
  - 잔류 프로세스:
    - `Ollama`, `ollama`, `WhisperKitPersistentWorker`, `Python`
  - 해석:
    - fresh app 1회에서는 `critical`이 재현되지 않았다.
    - 다만 종료 직후 worker residency는 남고, 2초 settle 뒤 RSS는 크게 줄어든다.
    - 다음 패스는 trim 호출 비용보다 warm session에서 compressed memory가 `critical`로 넘어가는 조건과 LLM/STT residency 누적을 직접 재현하는 쪽이 우선이다.

## 후속 묶음 실행 - 2026-05-20 18:40~18:56

- 범위: Action item `10`, `16`
- 목적: 생성 완료 후 놓칠 수 있는 AI/STT/LLM release를 한 번 더 보강하고, 마카오 반복 실앱에서 `critical`과 `app_unreachable` 중 실제 남은 병목을 분리한다.

### 코드 변경

- `ui/main/main_runtime_cleanup.py`
  - post-generation GC가 `_post_generation_models_release_requested`가 남아 있으면 강제 release를 한 번 더 재시도하도록 보강
  - 첫 async release 요청이 드롭돼도 warm-session cleanup이 후속 GC에서 다시 걸리게 함
- `tools/debug_guided_subtitle_memory.py`
  - `runtime_resource.active_labels`의 `pipeline/editor`를 processing으로 인식
  - 다음 run 시작 전 이전 run이 실제 idle로 내려왔는지 먼저 확인하도록 보강
- `tests/test_sidebar_terminal_layout.py`
  - post-generation GC release retry 회귀 테스트 2개 추가
- `tests/test_debug_guided_subtitle_memory.py`
  - `active_labels=pipeline` processing 판정 테스트 추가

### 자동 검증

- `./venv/bin/python -m unittest tests.test_debug_guided_subtitle_memory tests.test_sidebar_terminal_layout.SidebarTerminalLayoutTests.test_post_generation_cleanup_releases_models_immediately tests.test_sidebar_terminal_layout.SidebarTerminalLayoutTests.test_post_generation_gc_retries_model_release_when_flags_still_pending tests.test_sidebar_terminal_layout.SidebarTerminalLayoutTests.test_post_generation_gc_stops_retry_after_release_finishes -q`
  - 결과: `6 tests OK`
- `./venv/bin/python -m py_compile tools/debug_guided_subtitle_memory.py tests/test_debug_guided_subtitle_memory.py ui/main/main_runtime_cleanup.py tests/test_sidebar_terminal_layout.py`
  - 결과: `OK`
- `./venv/bin/python tools/check_maintenance_budget.py --json`
  - 결과: `issue_count=0`
- `git diff --check -- tools/debug_guided_subtitle_memory.py tests/test_debug_guided_subtitle_memory.py ui/main/main_runtime_cleanup.py tests/test_sidebar_terminal_layout.py`
  - 결과: `OK`

### 마카오 실앱 검증

- baseline idle:
  - fresh app ping/status에서 `pressure_stage=normal`, `free_memory_ratio=0.416`, `compressed_memory_ratio=0.0501`
- 반복 run 1:
  - artifact: `output/manual_verification/latest/20260520_action_batch_post_generation_release_retry_macau_repeat3_rerun/run_01/guided_memory_debug.json`
  - 결과:
    - `total_elapsed_sec=22.045`
    - `completed_via_snapshot=true`
    - `runtime_pressure_after=warning`
    - `memory_pressure_after=warning`
    - `subtitle_stage_after=stt_optimizer_threads_done`
    - `process_total_after=4`
    - `process_rss_after_gb≈0.957`
    - `process_rss_after_settle_gb≈0.087`
  - 관찰:
    - `메모리 critical: STT persistent worker 재사용 중단` 로그는 잡히지 않았다.
    - `subtitle_generation_monitor_after.json`에서는 `pressure_stage=warning`, `stage_trim_requested=true`, `stage_trim_summary.executed_count=1`
- 반복 run 2:
  - 앱 메인 로그에서는 실제 파이프라인이 끝까지 완료됐다.
  - 대표 로그:
    - `🧹 [자막 메모리] save_export_start: warning · rss=2.44GB · free=2.45GB`
    - `🧹 [자막 메모리] save_export_done: warning · rss=3.41GB · free=2.44GB`
    - `✅ 자막 생성 완료 (EditorPipeline 확정)`
    - `🧹 후처리 정리 완료: subtitle_generation_complete`
  - 하지만 자동화 표면에서는 `guided-subtitle-status`/`ping`가 계속 `app_unreachable` timeout으로 떨어져 run summary 파일은 끝까지 쓰지 못했다.

### 해석

- 이번 배치 후 첫 반복 run에서는 `critical`이 재현되지 않았고, post-generation release retry가 최소한 warm-session 잔류를 `critical`까지 밀어 올리는 현상은 줄인 것으로 보인다.
- 남은 직접 병목은 메모리 trim 자체보다, busy editor/save/export 동안 앱 명령 서버가 `app_unreachable`로 흔들리면서 반복 자동화와 status 수집이 끊기는 점이다.
- 다음 패스는 `guided-subtitle-status` fast snapshot / command server 응답성, 그리고 `save_export_*` 이후 idle 복귀 타이밍을 좁히는 쪽이 맞다.

## 후속 묶음 실행 - 2026-05-20 19:30~19:51

- 범위: Action item `12`
- 목적: `guided-subtitle-run`/`save_export_*` 중 `guided-subtitle-status`와 `ping`가 `app_unreachable`로 붕괴하는 지점을 줄이고, 마카오 실앱 repeat에서 남는 timeout 패턴을 다시 증거화한다.

### 코드 변경

- `core/automation/app_command_server.py`
  - UDP recv loop가 packet마다 worker thread를 분기하도록 변경
  - `ping`, `status`, `guided-subtitle-status`는 느린 stateful command와 분리해서 병렬 처리
  - stateful command는 별도 lock으로 직렬 유지
- `ui/main/app_command_bridge.py`
  - busy 상태(`ST_PROC`, `backend_active`, `runtime_resource.active_labels`)에서는 status fast-path가 Qt signal을 건너뛰고 fallback snapshot으로 즉시 응답하도록 보강
  - fallback snapshot도 short TTL cache에 저장해 busy polling 중 repeated fallback 재구성을 줄임
  - guided snapshot fallback payload를 더 직접 채우도록 보강
- `tests/test_app_command_server.py`
  - slow stateful command가 있어도 `guided-subtitle-status`가 막히지 않는 회귀 테스트 추가
  - stateful command 직렬 처리 유지 테스트 추가
- `tests/test_app_command_bridge.py`
  - busy owner에서 status signal을 건너뛰고 fallback/cache를 쓰는 회귀 테스트 추가

### 자동 검증

- `./venv/bin/python -m unittest tests.test_app_command_server tests.test_app_command_bridge tests.test_automation_command_client -q`
  - 결과: `58 tests OK`
- `./venv/bin/python -m py_compile core/automation/app_command_server.py ui/main/app_command_bridge.py tests/test_app_command_server.py tests/test_app_command_bridge.py tools/automation_command_client.py`
  - 결과: `OK`
- `git diff --check -- core/automation/app_command_server.py ui/main/app_command_bridge.py tests/test_app_command_server.py tests/test_app_command_bridge.py tools/automation_command_client.py`
  - 결과: `OK`

### 마카오 실앱 검증

- 앱 재시작 후 baseline:
  - `./venv/bin/python tools/appctl.py --timeout 2 status`
  - 결과: `ok=true`, `pressure_stage=normal`
- 1차 재현 확인:
  - `output/manual_verification/latest/20260520_action_batch_app_command_responsiveness_macau_repeat3`
  - 관찰:
    - run 1은 `guided_subtitle_started` 응답과 `06_completed.png`까지 확보
    - 이후 run 2 진입 전후 `guided_status_history.jsonl`과 `ping_history.jsonl`에 timeout이 길게 남음
    - 앱 메인 로그는 실제로 run 2까지 받아서 완료 로그를 남겼음
  - 해석:
    - recv-loop starvation 하나만의 문제는 아니고, busy 구간의 status/ping 응답면이 추가로 흔들린다.
- 2차 재검증:
  - 명령:
    - `./venv/bin/python tools/debug_guided_subtitle_memory.py --media '/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217225132_0079_D.MP4' --repeat 2 --output-dir output/manual_verification/latest/20260520_action_batch_app_command_responsiveness_macau_repeat2_v2`
  - 결과 요약:
    - run 1 `elapsed_sec=23.239`
    - run 2 `elapsed_sec=72.394`
    - `completed_via_snapshot=true` 2회
    - `critical_reuse_stop_runs=0`
    - `runtime_pressure_after=normal`, `memory_pressure_after=normal`
  - 산출물:
    - `output/manual_verification/latest/20260520_action_batch_app_command_responsiveness_macau_repeat2_v2/repeat_summary.json`
    - `output/manual_verification/latest/20260520_action_batch_app_command_responsiveness_macau_repeat2_v2/run_02/guided_status_history.jsonl`
    - `output/manual_verification/latest/20260520_action_batch_app_command_responsiveness_macau_repeat2_v2/ping_history.jsonl`
  - 남은 이슈:
    - run 2 `guided_status_history.jsonl`에 `wait_pre_run_idle`, `wait_processing_start`, `wait_processing_done` timeout이 계속 남음
    - `ping_history.jsonl`에도 `app_unreachable`가 여전히 반복됨
    - 즉, 이번 패치로 자동화 전체가 즉시 죽지는 않지만, live command 응답만으로 완료를 끝까지 추적하는 수준까지는 아직 못 갔다.

### 결론

- 이번 배치는 busy command 하나가 UDP recv loop를 독점하는 구조는 줄였다.
- 하지만 마카오 repeat2 실앱에서도 `ping`/`guided-subtitle-status` timeout collapse가 완전히 해소되지는 않았다.
- 다음 패스는 save/export 이후 구간의 status/ping 전용 ultra-light response 경로 또는 send/dispatch 실패 계측을 더 직접 넣어, 왜 packet-level reply가 끊기는지 확인해야 한다.

### 후속 조정

- `ui/main/app_command_bridge.py`
  - busy stale cache 재사용은 `2.5s` 상한으로 축소
  - `guided-subtitle-run` 시작 응답이 status cache를 즉시 prime하도록 유지
- `tests/test_app_command_bridge.py`
  - busy stale cache 재사용 상한 회귀 테스트 추가
  - `guided-subtitle-run` cache prime 회귀 테스트 추가

### 후속 검증

- `./venv/bin/python -m unittest tests.test_app_command_bridge tests.test_app_command_server tests.test_automation_command_client -q`
  - 결과: `61 tests OK`
- `./venv/bin/python -m py_compile ui/main/app_command_bridge.py tests/test_app_command_bridge.py`
  - 결과: `OK`
- `git diff --check -- ui/main/app_command_bridge.py tests/test_app_command_bridge.py ui/main/app_command_bridge_handlers.py core/automation/app_command_server.py tests/test_app_command_server.py`
  - 결과: `OK`

### 마카오 fresh-app smoke

- 명령:
  - `./venv/bin/python tools/debug_guided_subtitle_memory.py --media '/Users/u_mo_c/Downloads/마카오테스트/DJI_20260217225132_0079_D.MP4' --repeat 1 --output-dir output/manual_verification/latest/20260520_action_batch_app_command_responsiveness_macau_repeat1_v4`
- 결과:
  - `elapsed_sec=13.349`
  - `completed_via_snapshot=true`
  - `critical_reuse_stop_runs=0`
  - `runtime_pressure_after=normal`
  - `memory_pressure_after=normal`
- 산출물:
  - `output/manual_verification/latest/20260520_action_batch_app_command_responsiveness_macau_repeat1_v4/repeat_summary.json`
  - `output/manual_verification/latest/20260520_action_batch_app_command_responsiveness_macau_repeat1_v4/ping_history.jsonl`
- 해석:
  - indefinite stale reuse로 이전 run의 `ST_PROC`가 다음 run idle 판정까지 남는 회귀는 제거했다.
  - 다만 `ping_history.jsonl`에는 `app_unreachable` 1건이 여전히 남았고, item 12는 아직 종료 조건에 도달하지 못했다.

## One-command QA runner 최종 상태 - 2026-05-20

- 판정: `O`
- 범위:
  - `quick`: runner bootstrap + 실앱 smoke
  - `major`: Macau UX 핵심 4개
  - `full`: Macau UX 4개 + Tinyping 60초 `fast/auto/high`
- 최종 산출물:
  - `quick`: `output/manual_verification/latest/qa_suite_quick_20260520_174600`
  - `major`: `output/manual_verification/latest/qa_suite_major_20260520_183244`
  - `full`: `output/manual_verification/latest/qa_suite_full_20260520_193515`
- 최종 결과:
  - `quick`: `failed_count=0`
  - `major`: `scenario_count=4`, `failed_count=0`
  - `full`: `scenario_count=7`, `failed_count=0`
- 정리:
  - stale `dist/macos` bundle로 인한 `unknown_command`는 최신 bundle 재생성 후 해소됐다.
  - `editor_compact_macau`는 정적 `1.5초` 대신 현재 `editor_runtime.active_segment` 기반 동적 playhead 선택으로 안정화됐다.
  - `move_diamond`/`merge_diamond`는 현재 `diamond_left/right`의 `boundary_sec`를 기준으로 command를 조립하도록 바꿔 fixture drift를 흡수했다.
  - `full_media` 3건 실패는 기능 실패가 아니라 stdout parse 문제였고, runner가 마지막 JSON line fallback을 읽도록 보강한 뒤 해소됐다.
- 남은 위험:
  - runner는 최신 workspace 코드가 반영된 `dist/macos/AI Subtitle Studio.app` 기준으로 가장 안정적이다.
  - bundle이 stale이면 `unknown_command`나 fixture/state mismatch가 다시 보일 수 있으므로, 큰 command surface 변경 뒤에는 bundle regenerate를 먼저 수행한다.

## One-command QA runner 재검증 - 2026-05-20 21:01

- 실행 목적:
  - 최신 automation/app-command 변경이 반영된 번들 기준으로 official runner를 다시 실검증
- 사전 조치:
  - `./packaging/macos/build_app_bundle.sh`
  - 최근 app-command surface 변경 이력이 있어 stale bundle 가능성을 먼저 제거했다.
- 실행:
  - `./venv/bin/python tools/qa_suite_runner.py full`
- 결과:
  - `profile=full`
  - `scenario_count=7`
  - `passed_count=7`
  - `failed_count=0`
- 산출물:
  - `output/manual_verification/latest/qa_suite_full_20260520_210149`
  - `output/manual_verification/latest/qa_suite_full_20260520_210149/suite_result.json`
- scenario 요약:
  - `editor_compact_macau`: pass
  - `video_menu_macau`: pass
  - `save_export_macau`: pass
  - `menu_stt_lora_macau`: pass
  - `tinyping_fast_60s`: pass (`pipeline_elapsed_sec=9.227`, `total_elapsed_sec=21.801`)
  - `tinyping_auto_60s`: pass (`pipeline_elapsed_sec=9.09`, `total_elapsed_sec=44.51`)
  - `tinyping_high_60s`: pass (`pipeline_elapsed_sec=19.015`, `total_elapsed_sec=19.105`)
- 분류:
  - 실패 없음
  - stale bundle 의심 경로는 번들 재생성 후 재검증으로 해소 확인
- 해석:
  - 이번 run에서는 `app_sequence`와 `full_media` 모두 집계 문제 없이 바로 통과했다.
  - 따라서 현재 기준 official one-command QA runner는 최신 번들 상태에서 `full`까지 재통과한 상태다.

## 아이디어 통합 실행 Phase 1 - 2026-05-21 02:49

- 실행 범위:
  - `idea_item.md` Phase 1: stage/resource observability 및 app-command 응답성 계측
  - 자막 품질 게이트, 모델 선택, UI/UX 동작은 변경하지 않음
- 코드 변경 요약:
  - `core/runtime/stage_metrics.py` 추가
  - `ping/status/guided-subtitle-status` 경로에 compact stage metric 노출
  - app command server의 wait/busy/queue_depth 계측
  - memory trim summary와 selected Swift native bridge encode/native/decode metric 연결
- 벤치마크 산출물:
  - `output/manual_verification/latest/idea_full_execute_20260521-0228/summary.md`
- 성능 비교:
  - Macau fast r3: `7.618s` -> `7.608s`, final segment `5 -> 5`
  - X5 fast 60s r3: `9.856s` -> `9.973s`, final segment `17 -> 17`
  - Tinyping fast 60s: total `23.020s` -> `21.815s`, final/raw `18/15 -> 18/15`
  - Tinyping auto 60s: total `46.588s` -> `41.904s`, final/raw `18/15 -> 18/15`
  - Tinyping high 60s: total `29.372s` -> `18.675s`, final/raw `16/16 -> 16/16`
- 해석:
  - X5의 `+~1.2%`는 observability-only 변경의 noise/watch로 보고, 속도 개선 알고리즘으로 주장하지 않는다.
  - Tinyping 개선은 cache/warm-state 영향이 섞여 있어 회귀 비교 기준으로만 사용한다.
  - aggressive quarter-parallel STT/LLM 및 native deterministic batch 승격은 아직 parity 구현/품질 게이트 전이므로 채택하지 않았다.
- 검증:
  - `./venv/bin/python -m unittest tests.test_runtime_stage_metrics tests.test_app_command_server tests.test_app_command_bridge tests.test_runtime_memory_manager tests.test_automation_command_client tests.test_runtime_multi_process -q`
    - 결과: `119 tests OK`
  - `./venv/bin/python tools/check_maintenance_budget.py --json`
    - 결과: `ok=true`
  - `./venv/bin/python tools/qa_suite_runner.py full`
    - 결과: `failed_count=0`
    - 산출물: `output/manual_verification/latest/qa_suite_full_20260521_024927`

## STT rolling window 병렬 실험 - 2026-05-21 13:48

- 실행 범위:
  - 기존 High+piecewise drift 품질 경로 유지
  - rolling STT window의 최종 확정 순서는 유지하고, window 수집을 guarded default로 병렬화
  - window chunk dir가 전체 부모 청크를 재인식하지 않도록 경계 WAV를 실제 window 범위로 slice
- X5 180초 STT-only 비교:
  - baseline `mode_high_piecewise_drift`: `106.515s`, quality `77.315`, raw/final `60/57`
  - 기존 rolling window 병렬 경로: `94.293s`, quality `77.315`, raw/final `60/57`
  - 기본 High 경로 재검증: `94.614s`, quality `77.315`, raw/final `60/57`
  - 개선: 약 `11.5%` faster, 품질/세그먼트 수 동일
  - 적용 정책: `stt_window_parallel_enabled` 기본 활성화, 메모리 `critical` 또는 병렬 worker 실패 시 serial fallback, 기본 자동 병렬도는 2워커
- 폐기 확인:
  - forced 60초 quarter window는 `128.951s`, quality `75.351`, raw/final `79/71`로 느리고 품질이 낮아 `waste_action_item.md`에 기록
- 산출물:
  - 요약 복사본: `output/manual_verification/latest/stt_window_parallel_20260521_1348/summary.md`
  - baseline: `.codex_work/benchmarks/subtitle_pipeline_variants/20260521_134359/benchmark_results.json`
  - forced 60초 폐기: `.codex_work/benchmarks/subtitle_pipeline_variants/20260521_134130/benchmark_results.json`
  - 기존 rolling window 병렬 검증: `.codex_work/benchmarks/subtitle_pipeline_variants/20260521_134652/benchmark_results.json`
  - 기본 High 경로 재검증: `.codex_work/benchmarks/subtitle_pipeline_variants/20260521_140147/benchmark_results.json`
- 검증:
  - `./venv/bin/python -m unittest tests.test_media_processor_overlap -q`
    - 결과: `73 tests OK`
  - `./venv/bin/python -m py_compile core/audio/media_processor_transcribe.py tests/test_media_processor_overlap.py`
    - 결과: OK
  - `./venv/bin/python tools/check_maintenance_budget.py --json`
    - 결과: `ok=true`
  - `git diff --check -- core/audio/media_processor_transcribe.py tests/test_media_processor_overlap.py idea_item.md waste_action_item.md test_result.md output/manual_verification/latest/stt_window_parallel_20260521_1348/summary.md`
    - 결과: OK
  - `./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --suite modes --variants mode_high_piecewise_drift --duration-sec 180 --llm-model '사용 안함 (benchmark)' --keep-artifacts`
    - 결과: `94.614s`, quality `77.315`, raw/final `60/57`

## STT resource aggressive X5 검증 - 2026-05-21 14:08

- 실행 범위:
  - X5 180초 STT-only에서 리소스 사용량을 늘리는 window 후보를 비교
  - 폐기된 forced 60초 quarter는 반복하지 않음
  - 자막 품질/세그먼트 수를 기준으로 채택 여부 판단
- 비교:
  - 이전 guarded default: `94.614s`, quality `77.315`, raw/final `60/57`
  - 90초 aggressive window workers: `130.741s`, quality `76.587`, raw/final `69/69`
  - 180초 three-minute window: `57.711s`, quality `79.049`, raw/final `52/53`
  - 적용 후 공식 runner 재검증: `58.490s`, quality `79.049`, raw/final `52/53`
  - X5 전체 404.137초 공식 runner: `157.540s`, quality `74.588`, raw/final `110/106`
- 판정:
  - 90초 aggressive window는 느리고 과분할되어 `waste_action_item.md`에 폐기 기록
  - High 기본 rolling STT window를 `180초`로 변경
  - 긴 영상에서는 180초 window 수가 2개 이상일 때 normal memory에서 최대 4개 worker까지 병렬 수집하도록 조정
  - X5 전체에서는 180초 window 3개가 실제로 3 worker 병렬 실행됨
  - 병렬 전체 실행 중 pressure `critical`이 발생해 일부 persistent worker가 자동 정리되었으므로, 더 공격적인 worker cap 증가는 보류
- 산출물:
  - 요약: `output/manual_verification/latest/stt_resource_aggressive_20260521_140857/summary.md`
  - 원본 JSON: `.codex_work/benchmarks/stt_resource_aggressive/20260521_140857/benchmark_results.json`
  - 공식 runner JSON: `output/manual_verification/latest/stt_resource_aggressive_20260521_140857/official_benchmark_results.json`
  - X5 전체 runner JSON: `output/manual_verification/latest/stt_resource_aggressive_20260521_140857/x5_full_benchmark_results.json`

## X5 High post-STT hot path/resource 검증 - 2026-05-22 23:31

- 실행 범위:
  - 자막 품질 정책, STT2 선택 기준, LLM 모델/게이트 변경 없이 post-STT UI/status/resource hot path만 축소
  - STT live preview 중 동기 4K thumbnail extraction 차단
  - `guided-subtitle-status` compact 필드 유지
  - `subtitle_optimize` resource label/native allocator budget 추가
  - roughcut LLM 시작 전 `critical` pressure 짧은 gate 추가
- 검증:
  - Python compile: OK
  - `tests/test_app_command_bridge.py tests/test_app_command_server.py`: 65 passed
  - `tests/test_runtime_multi_process.py tests/test_runtime_stage_metrics.py`: 37 passed
  - `tests/test_editor_roughcut_draft.py`: 56 passed
  - `tests/test_project_segment_reload.py`: 69 passed
  - `swift test --package-path native/macos/AIStudioNative --filter NativeResourceAllocatorTests`: 7 passed
  - `swift build -c release --package-path experiments/whisperkit_persistent_worker`: OK
- X5 High 실앱 결과:
  - `guided-subtitle-status`: `backend_active=false`, `last_stage_key=completed`, `roughcut_state.status=done`, `roughcut_state.major_count=4`
  - 최종 runtime pressure: `normal`, RSS `0.9865GB`, free memory `6.1085GB`
  - 저장 subtitle count: project `63`, final SRT `63`
- 판정:
  - hot path/resource 변경은 실앱 완료와 pressure 회복을 확인
  - 기존 active item reference의 X5 저장 subtitle count `107`과 이번 저장 count `63`이 달라 ACTION_ITEMS 완료 삭제는 보류
- 산출물:
  - `output/manual_verification/latest/20260522_x5_hotpath_resource_after_patch/verification_summary.md`
  - `output/manual_verification/latest/20260522_x5_hotpath_resource_after_patch/final.png`
  - `output/manual_verification/latest/20260522_x5_hotpath_resource_after_patch/final_guided_status.json`
