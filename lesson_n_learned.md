# lesson_n_learned.md

이 파일은 반복하면 안 되는 판단, 실험, 진단 실수를 저장한다.

## 사용 규칙

- `ACTION_ITEMS.md` 실행 또는 새 아이디어 발굴 전에 반드시 이 파일과 `waste_action_item.md`를 먼저 확인한다.
- 이미 폐기된 아이디어는 같은 조건에서 다시 제안하거나 실행하지 않는다.
- 같은 아이디어를 재검토하려면 새 하드웨어, 새 모델, 새 benchmark, 새 계측처럼 이전 결론을 뒤집을 근거를 먼저 적는다.
- lesson은 짧게 남기되, 가능하면 원인, 금지할 반복 행동, 다시 해야 할 검증을 함께 적는다.

## Lessons Learned

### 2026-06-28

- generated-video acceptance를 자막 개수, text/timing 점수, overlap만으로 pass 처리하지 않는다.
  - 이유: `20260628_010403` NAS-off generated-video run은 legacy benchmark acceptance가 `accepted=true`였지만, 직접 media/SRT 검증에서 영상 길이 `180.584s`를 넘어 `182.032s`까지 자막이 생성됐고, out-of-duration row `17`, sub-0.3s row `16`, 59.792s tail row `1`이 확인됐다.
  - 다음 원칙: generated fixture 검증은 media duration bound, minimum subtitle duration, long-tail segment gate를 함께 통과해야 한다. Global canvas duration을 subtitle `last_end`에서 자동으로 잡은 결과를 영상 길이 검증으로 오해하지 않는다.

- VAD/STT timing consensus에서 전체 파일급 VAD span을 단일 자막 row에 union하지 않는다.
  - 이유: `20260628_010403`에서 broad VAD `[0.0, 180.912]`가 STT1 row와 union되면서 row 38이 `121.120-180.912`로 늘고, 뒤 row들이 0.05s tail fragments로 밀렸다.
  - 다음 원칙: STT1/VAD-only union은 VAD와 STT1 span이 start/end/duration tolerance 안에서 비슷할 때만 허용한다. Broad VAD는 row-level timing proof가 아니라 coverage hint로만 다룬다.

### 2026-06-27

- 자막 생성 지연을 컷 경계 병목으로 바로 단정하지 않는다.
  - 이유: HeyDealer 180s High run에서 전체 pipeline은 약 60초였지만 cut-boundary cProfile owner rows의 top cumulative time은 `0.000602s`, confirmed cut split/snap은 `0.000525s`였다.
  - 다음 원칙: 성능 진단은 non-profile repeat elapsed와 profiler owner diagnosis를 분리하고, reference-scored fixture로 raw/final count, quality, timing MAE, final overlap, save/global-canvas stability를 함께 확인한 뒤에만 trim을 제안한다.

- reference fixture preflight를 파일 존재/파싱 통과로만 승인하지 않는다.
  - 이유: X5 180s cached WAV는 이름상 `후반`처럼 보였지만 실제 음성은 `X5_전반` 프로젝트 SRT와 정렬됐다. `X5_후반` SRT도 파일/파싱 preflight는 통과했지만 reference benchmark quality `23.234`, text `4.756`, timing MAE `3.3362s`로 semantic mismatch였다.
  - 다음 원칙: media/SRT 조합은 `verify_reference_fixture_availability.py` 후 반드시 `benchmark_subtitle_pipeline_variants.py --reference-srt`와 `evaluate_reference_benchmark_acceptance.py`까지 통과해야 latency trim 판단에 쓴다. 파일명이나 SRT parse 성공만으로 reference-fit을 주장하지 않는다.

### 2026-05-20

- 수동 저장 직후 러프컷 LLM이 뜨면 editor 러프컷 타이머만 보지 않는다.
  - 이유: 외부 SRT/프로젝트 없는 상태의 수동 저장은 저장용 프로젝트를 자동 생성하며, `create_project()` 기본 prefill 경로가 러프컷 LLM을 동기 실행할 수 있다.
  - 다음 원칙: 저장 버그는 `_on_save()` 후속 타이머와 함께 `_auto_save_project()` / `create_project(prefill_analysis_artifacts=...)` 호출 인자를 먼저 확인한다.

- STT/LLM 속도 최적화에서 cleanup을 무작정 줄이는 방식은 반복하지 않는다.
  - 이유: `cut_prescan_done cleanup 제거`와 `subtitle_optimize_done warning-stage GPU trim 제거`는 일부 짧은 run에서만 좋아 보였고 X5 평균은 악화됐다.
  - 다음 원칙: cleanup/trim을 줄이기 전에 `stage_trim.elapsed_ms`, process residency, X5/Tinyping 반복 평균을 먼저 확인한다.

- 짧은 Macau 단건 개선만 보고 채택하지 않는다.
  - 이유: Macau는 빠른 smoke에는 좋지만 X5/Tinyping long-flow 병목을 대표하지 못할 수 있다.
  - 다음 원칙: 성능 후보 채택은 Macau + X5 + 가능하면 Tinyping에서 평균, p95, 품질 지표를 함께 본다.

- `Terminated: 15`를 모델 크래시로 바로 단정하지 않는다.
  - 이유: 2026-05-20에는 mlx-whisper 로그 직후 앱 자체 exit watchdog이 Python에 SIGTERM을 보내 `.command` 터미널에 `Terminated: 15`가 찍힌 것이었다.
  - 다음 원칙: crash/termination 로그는 마지막 모델 로그가 아니라 process owner, signal source, app shutdown path를 함께 본다.

- 최적화 중 UI/UX를 같이 손대지 않는다.
  - 이유: 성능 회귀와 UI 변경이 섞이면 원인 분리가 어려워지고 사용자가 명시하지 않은 UX 변경이 된다.
  - 다음 원칙: UI/UX 변경이 필요해 보이면 별도 owner-decision item으로 남기고 승인 전에는 구현하지 않는다.

### 2026-05-21

- 앱 자동화 status/ping payload에 상세 stage history를 무제한 싣지 않는다.
  - 이유: 앱 명령은 UDP 응답이고 `APP_COMMAND_BUFFER_SIZE=65535` 제한이 있다. recent logs, guided snapshot 상태, editor runtime에 stage detail까지 길게 붙이면 응답 자체가 흔들릴 수 있다.
  - 다음 원칙: status/guided-subtitle-status에는 compact `resources + recent_events`만 싣고, full stage breakdown은 artifact나 별도 디버그 명령으로 분리한다.

- QA runner의 `app_bootstrap_failed`를 곧바로 code regression으로 보지 않는다.
  - 이유: 2026-05-21 `quick` 첫 실행은 이미 떠 있던 unreachable live app 때문에 duplicate launcher가 종료된 environment issue였다.
  - 다음 원칙: `AI Subtitle Studio is already running` 또는 `app_unreachable`가 함께 보이면 `pgrep/ps`로 stale app을 확인하고 정리한 뒤 같은 profile만 재실행한다.

- STT/LLM warm 유지 테스트는 host memory 상태에 의존하지 않게 만든다.
  - 이유: 실제 Mac의 memory pressure가 warning/critical이면 정책상 warm worker/LLM residency가 꺼져 테스트가 비결정적으로 흔들릴 수 있다.
  - 다음 원칙: warm 유지/해제 unit test는 `current_resource_snapshot`을 normal 또는 critical로 명시 patch하고, 실제 memory pressure는 integration artifact에서 확인한다.

- STT1/STT2 full-parallel이 빠르다고 High 기본값으로 바로 올리지 않는다.
  - 이유: 2026-05-21 X5 60초에서 full-parallel STT는 selective보다 약 3배 빨랐지만 final segment count와 reference quality가 떨어졌다.
  - 다음 원칙: 병렬 STT는 품질 barrier, word precision 보정, segment count 회복 조건이 같이 붙은 후보로만 다시 실험한다.

- native helper benchmark의 speedup만 보고 adoption을 `native`로 표시하지 않는다.
  - 이유: 2026-05-21 Swift/native policy mini benchmark에서 속도는 크게 빨랐지만 LLM candidate count, deep rerank chunk, batch count, LoRA top5 parity가 맞지 않았다.
  - 다음 원칙: native adoption report는 speedup과 parity를 동시에 통과해야 `native`로 표시하고, parity 실패는 `blocked_quality_mismatch`로 남긴다.

- Swift policy helper benchmark는 experimental gate를 실제로 켠 뒤 측정한다.
  - 이유: `native_swift_policy_experimental_enabled`가 빠지면 wrapper가 `None`으로 빠져 disabled path를 native timing처럼 기록할 수 있다.
  - 다음 원칙: benchmark fixture에는 experimental gate를 명시하고, LoRA처럼 동점이 많은 scoring은 native sort tie-break까지 Python 기준과 맞춘다.

- Qt Widgets/QPainter 2D 전환에서는 legacy setting true를 그대로 신뢰하지 않는다.
  - 이유: `editor_rendering_scenegraph_enabled=true`가 user/default settings에 남아 있으면 QML/SceneGraph가 다시 켜져 macOS 합성 잔상과 black surface 위험이 되살아날 수 있다.
  - 다음 원칙: QML/SceneGraph는 새 opt-in flag나 명시 env가 있을 때만 켜고, 기본 렌더링 owner는 `qwidget-2d`로 유지한다.

- Fast 모드 성능 수치를 품질 동일 후보 수치와 섞지 않는다.
  - 이유: 2026-05-21 X5 10회 반복에서 `mode_fast`는 평균 `10.373s`였지만 품질 gate가 `0/10`이었다.
  - 다음 원칙: 최종 알고리즘 선택은 품질 gate 통과 후보끼리만 비교하고, Fast 모드는 별도 속도 모드로 기록한다.

- spoken full-media 검증에서 자막 0개를 pass로 두지 않는다.
  - 이유: 2026-05-21 `tinyping_auto_60s`가 `raw/final=0/0`인데 verifier verdict가 pass로 집계될 수 있음을 확인했다.
  - 다음 원칙: VAD/chunk가 있는 non-trivial slice는 raw 또는 final subtitle이 0개면 `empty_subtitle_output:*`로 실패시킨다.

- bundled macOS app은 `.app` 실행 파일만 보고 stale 여부를 판단하지 않는다.
  - 이유: 실제 runner가 붙는 프로세스는 `dist/macos/AI Subtitle Studio.app/Contents/Resources/app/main.py`를 실행하는 Python일 수 있다.
  - 다음 원칙: app restart 전에는 bundled Python main process와 zombie/종료 중 PID를 구분하고, alive process만 blocker로 취급한다.

- 자동화 status/ping은 UI 최신성보다 응답 생존성이 우선이다.
  - 이유: 2026-05-21 automation-4 재검증에서 status 응답이 커지거나 busy 구간에 새 runtime snapshot을 만들면 실제 기능은 동작해도 `app_unreachable`로 오판될 수 있었다.
  - 다음 원칙: status fallback은 cached runtime resource만 사용하고, UDP 응답은 compact/minimal fallback을 반드시 거치게 한다. 상세 원인은 artifact와 단계 로그로 따로 본다.

- compact editor QA에서 stale line/side selection을 기능 실패로 단정하지 않는다.
  - 이유: smart split 후 segment가 아주 짧아지면 이전 `--line 1 --side right` 명령은 현재 graph와 맞지 않아 `diamond_pair_missing`을 만들 수 있다.
  - 다음 원칙: 자동화 runner는 현재 status에 boundary pair가 없으면 stale line을 버리고 `closest` diamond로 복구한다. 실제 기능 회귀는 editor runtime pair가 있는 상태에서 재현될 때만 본다.

- playhead/shadow playhead repaint를 성급히 dirty-strip 최적화로 되돌리지 않는다.
  - 이유: 사용자가 보고한 타임라인 잔상/텍스트 겹침은 부분 repaint와 다중 paint owner가 섞일 때 재발하기 쉽다. 현재 single-owner 2D 경로는 전체 canvas repaint로 잔상 안정성을 우선한다.
  - 다음 원칙: playhead-only dirty rect는 Macau visual smoke에서 잔상 없음이 증명될 때만 별도 실험으로 열고, 기본 경로는 `TimelineSingleOwnerPlayheadInvalidation` audit가 지키는 full canvas repaint를 유지한다.

- UI hot path fallback은 조용히 삼키지 말고 한 번만 원인을 남긴다.
  - 이유: viewport clip 또는 voice-activity lane refresh 실패는 사용자가 보는 잔상/누락으로 이어질 수 있지만, 매 프레임 로그를 찍으면 편집 성능이 흔들린다.
  - 다음 원칙: 복구 가능한 UI 예외는 기존 복구 동작을 유지하되, key별 one-shot nonfatal WARN으로 남기고 반복 로그는 막는다.

- 완료된 `ACTION_ITEMS.md` 항목을 다시 실행하라는 요청이 오면 폐기 후보를 새 근거 없이 재구현하지 않는다.
  - 이유: `mode_fast`는 X5 10회 rerun에서도 quality gate `0/10`이었고, 이전 폐기 결론을 뒤집지 못했다.
  - 다음 원칙: active queue가 비어 있으면 benchmark/QA를 refresh하고 문서를 닫는다. 폐기 후보 재실행은 새 모델, 새 fixture, 새 품질 보정, 새 benchmark 근거가 있을 때만 한다.

- 장시간 High 검증은 성공 여부와 별개로 memory pressure snapshot을 같이 기록한다.
  - 이유: Tinyping long high 1회는 pass했지만 run 전후 pressure snapshot이 `critical`을 기록했다.
  - 다음 원칙: long high 최적화는 elapsed만 보지 말고 `runtime_monitor`, `subtitle_generation_monitor`, peak RSS, residual worker를 함께 본다.

### 2026-05-27

- 하단 타임라인/글로벌 캔버스 영역을 전체 0-margin으로 붙이지 않는다.
  - 이유: 위쪽 gap을 없애는 과정에서 root bottom margin까지 0으로 만들면 하단 파란 테두리/상태 라인이 창 끝에 붙어 클리핑되거나 사라져 보일 수 있다.
  - 다음 원칙: 위쪽과 내부 타임라인 gap은 0으로 줄이더라도, 하단 외부에는 최소 3-4px clearance를 유지하고 실제 앱에서 하단 테두리 표시를 확인한다.

- 글로벌 미니맵 초록 viewport 테두리는 root margin만으로 보호했다고 판단하지 않는다.
  - 이유: outer bottom margin이 있어도 QPainter viewport rect 하단선 자체가 minimap widget 최하단에 가까우면 선 두께의 일부만 보일 수 있다.
  - 다음 원칙: 하단 테두리 문제는 outer margin과 minimap 내부 bottom clearance를 함께 확인하고, 초록 viewport 하단선은 최소 16px 위에서 그린다.

- 하단 초록 viewport 테두리가 전부 보이는 것만으로 OK 처리하지 않는다.
  - 이유: 8px clearance는 선이 잘리지 않는 최소 수준일 뿐, 실제 앱에서는 하단 조작 영역과 붙어 보여 여백이 부족하다는 판단을 받았다.
  - 다음 원칙: 하단 테두리 QA는 "선이 보임"이 아니라 "선 아래 여유가 체감됨"을 기준으로 삼고, root bottom margin과 minimap 내부 bottom clearance를 16px 이상으로 둔다.

- 파일 열기 foreground 동작보다 에디터 AI 모델 정리를 먼저 실행하지 않는다.
  - 이유: `editor-release-ai-models`가 Ollama/STT/GPU 정리를 잡고 있으면 사용자가 파일 열기를 눌러도 다이얼로그/선택 dispatch가 정리 완료 로그 뒤로 밀려 보일 수 있다.
  - 다음 원칙: 파일/폴더 다이얼로그 진입 직전에는 foreground file-open priority를 세우고, post-generation AI release와 cache trim은 파일 선택이 dispatch된 뒤 재시도한다.

- 하단 메뉴 버튼에서 띄운 확인/오류 팝업을 버튼 parent 기준으로 중앙 정렬하지 않는다.
  - 이유: parent가 `GlobalMenuBar`이면 QML/QMessageBox가 앱 중앙이 아니라 하단 바 중앙에 떠서 사용자가 팝업 위치를 NG로 판단한다.
  - 다음 원칙: 모든 확인/오류/정보 modal은 즉시 클릭한 버튼이 아니라 visible top-level window 중심을 기준으로 배치하고, 하단 버튼 호출 케이스를 별도 테스트한다.

- 정밀 자막 작업에서 cut boundary point와 clip boundary span을 섞지 않는다.
  - 이유: `boundary_times`에는 float 초 단위 컷 포인트가 들어올 수 있는데 이를 `clip_boundaries`로 넘기면 recheck path가 `.get()`을 호출하며 `'float' object has no attribute 'get'`로 실패한다.
  - 다음 원칙: 품질 pipeline의 `clip_boundaries`에는 `{start,end}` span row만 넘기고, 컷 포인트/임시 경계는 magnet과 canvas state에만 전달한다.

- 사용자가 버튼으로 실행하는 수동 작업은 완료/실패 때만 로그를 남기지 않는다.
  - 이유: 정밀 자막 작업처럼 긴 작업이 시작 직후 UI status만 바꾸면 터미널 로그 위젯과 macOS Terminal에서는 아무 작업도 안 하는 것처럼 보이고, 중간 단계 디버깅도 어렵다.
  - 다음 원칙: 수동 작업은 시작 예약, 실제 시작, 주요 단계, 완료, 실패를 `get_logger().log(..., stage=...)`로 UI 터미널에 남기고, macOS Terminal 디버깅용 상세 값은 `terminal_debug(..., stage=...)`로 함께 남긴다.

- 정밀/후처리처럼 VAD, 오디오 준비, Whisper를 포함하는 수동 작업을 UI 스레드에서 실행하지 않는다.
  - 이유: `QTimer.singleShot(0, heavy_func)`는 비동기가 아니라 다음 Qt 이벤트에서 메인 스레드가 무거운 작업을 실행하므로 macOS 모래시계/무응답으로 보인다.
  - 다음 원칙: 무거운 수동 작업은 background worker에서 계산하고, status/progress/result/error만 Qt signal로 UI 스레드에 반영한다. UI 반영 단계에서 실패해도 running 상태와 worker 핸들은 반드시 해제한다.

- 하단 파란 테두리/자막선은 외부 margin 하나만 올려서 해결했다고 판단하지 않는다.
  - 이유: root bottom margin을 올려도 글로벌 캔버스 내부 subtitle lane의 파란 하단선과 Timeline focus border가 각각 위로 올라오지 않으면 실제 앱에서는 여전히 하단 버튼/창 경계에 묻혀 안 보일 수 있다.
  - 다음 원칙: 하단 라인 QA는 root bottom clearance, global canvas content bottom pad, timeline focus border bottom clearance를 함께 올리고 테스트로 잠근다.

- 앱 시작 직후 홈 자동 소스 스캔/LLM 점검을 즉시 돌려 파일 선택과 경쟁시키지 않는다.
  - 이유: 첫 실행 직후 사용자는 보통 바로 파일/프로젝트를 고르는데, iCloud/NAS 스캔, LLM warmup/preflight, 모델 확인, post-generation AI release retry가 같은 시간대에 붙으면 macOS 파일 선택기가 늦게 반응한다.
  - 다음 원칙: startup optional work는 짧은 quiet window 뒤로 미루고, 파일/홈 foreground action이 감지되면 optional startup과 AI release retry가 파일 선택 dispatch 이후까지 양보하게 한다.

- 글로벌 캔버스 하단 콘텐츠 pad는 초록 viewport 테두리보다 작게 두지 않는다.
  - 이유: 초록 테두리 하단선 clearance가 콘텐츠 bottom pad보다 크면 보라/파란 글로벌 캔버스 막대가 테두리 바깥 아래로 내려가 보인다.
  - 다음 원칙: 초록 테두리 위치가 승인된 상태에서는 테두리를 다시 움직이지 말고, 글로벌 캔버스의 content bottom pad를 viewport bottom clearance 이상으로 맞춘다.

- 하단 마진에 파란 선을 보이게 하려고 별도 하단선을 추가하거나 포커스 테두리를 크게 위로 당기지 않는다.
  - 이유: 마진 영역에는 파란 박스의 하단선 하나만 딱 맞게 들어가야 하는데, 별도 선이나 과한 bottom clearance를 주면 빨간 박스 영역처럼 여러 줄이 겹쳐 보인다.
  - 다음 원칙: 하단 포커스 표시는 선을 새로 그리는 문제가 아니라 기존 파란 박스의 height/geometry를 border 두께만큼만 조절해서 네모 박스가 유지되게 처리한다.

- 글로벌 캔버스 초록 viewport 하단 마진을 별도 보정선으로 처리하지 않는다.
  - 이유: 2026-05-27 실제 앱에서 초록 viewport 박스 아래에 빨간 박스로 지적된 하단 여백이 남았고, 선을 추가하면 네모 박스가 아니라 겹친 줄처럼 보였다.
  - 다음 원칙: 초록 viewport 하단은 `GLOBAL_CANVAS_VIEWPORT_BOTTOM_CLEARANCE`와 `QRect` height로만 맞추고, `drawRect` 이후 별도 `drawLine`을 덧그리지 않는다.

- 하단 파란 포커스 박스가 안 보일 때 글로벌 캔버스 내부 선만 조정하지 않는다.
  - 이유: 실제 문제는 하단 global menu와 timeline frame이 너무 가까워서 파란 focus box 하단이 버튼/창 경계에 먹히는 것이었고, 내부 미니맵/viewport 선 조정만으로는 해결되지 않았다.
  - 다음 원칙: 파란 하단선 표시 문제는 `EDITOR_TIMELINE_BOTTOM_CLEARANCE`로 timeline frame 전체를 위로 올리고, 비디오 프리뷰 폭은 줄어든 높이의 16:9 계산을 따라 다시 잠근다.
