# Performance Ideas And Execution Plan

이 파일은 성능 아이디어, 이전 action/native queue, 실행 순서, QA 게이트를 합친 단일 실행 원천이다.
사용자가 `아이디어 전부 실행해`라고 말하면 아래 active queue를 기준으로 진행한다.

## Hard Rules

- 자막 품질이 속도보다 우선이다.
- UI/UX는 명시 요청 없이 변경하지 않는다.
- 모델 축소, STT2 생략, LLM 생략, 품질 게이트 완화는 기본 최적화 후보가 아니다.
- Apple Silicon에서는 Apple Neural Engine, 즉 `ANE` 기준으로 표현한다. Core ML이 ANE/GPU/CPU 배치를 결정하고, Metal/MLX/whisper.cpp는 주로 GPU/CPU 경로로 검증한다.
- PyTorch MPS는 과거 `metal gpu stream` crash 근거가 있으므로 production default가 아니라 격리 실험 후보로만 둔다.
- native 승격은 Swift/C++가 Python과 parity를 갖고 real fixture에서 같거나 빠를 때만 한다.
- live Qt widget, mutable editor state, subprocess orchestration, model-worker ownership, UI callback은 native로 통째 이전하지 않는다.
- 자막 에디터 상호작용 표면은 2D-only이다. 자막 본문 편집, 자막 세그먼트 편집/생성/삭제, 플레이헤드 이동, 컷 경계, 다이아몬드, waveform/minimap 렌더링에 3D view, QML SceneGraph, OpenGL/Metal-backed UI surface를 새 default로 도입하지 않는다.
- 전체 앱 shell, 메뉴, 팝업, 다이얼로그의 새 UI 기본값은 `Qt Widgets`로 고정한다. QML은 새 UI default에서 제외하고, Metal은 UI renderer가 아니라 native compute 후보로만 검토한다.
- 아이디어 발굴 또는 실행 전 `waste_action_item.md`와 `lesson_n_learned.md`를 먼저 읽고, 폐기된 아이디어를 새 근거 없이 반복하지 않는다.
- 실패/무효 후보는 `waste_action_item.md`에 hypothesis, change, metrics, quality, artifact, rejection reason을 남긴다.
- 반복하면 안 되는 진단/실험/운영 실수는 `lesson_n_learned.md`에 남긴다.
- 정상 완료된 idea/action/native item은 이 파일에서 삭제한다. 완료 이력은 필요할 때만 `test_result.md`, release note, `output/manual_verification/latest/`, `waste_action_item.md`, 또는 `lesson_n_learned.md`에 남긴다.

## Active Execution Queue

- 없음.

모든 현재 idea/action/native 최적화 항목은 2026-05-21 기준 실행, 검증, 채택/폐기 분류가 끝났다.
같은 요청이 다시 들어오면 먼저 최신 `quick/major/full`과 핵심 benchmark를 refresh하고, 새 계측 근거 없이 폐기 후보를 다시 구현하지 않는다.

## Current Selection

- 최종 품질 보존 후보: `mode_high_piecewise_drift`
- 선택 이유: X5 60초 reference 기준 10회 반복에서 품질 gate `10/10` 통과.
- 유지 기본값:
  - 기존 `candidate1` 품질 보존 파이프라인.
  - stage-owned STT/LLM resource policy.
  - quarter prescan metadata.
  - Qt Widgets/QPainter 2D editor rendering.
  - status/QA hardening.
- 기본 승격 금지:
  - `mode_fast`를 품질 동일 기본 알고리즘으로 승격.
  - STT1/STT2 full-parallel을 High 기본값으로 승격.
  - Swift/native policy helper를 parity와 speedup 동시 통과 없이 default 승격.
  - QML/SceneGraph/Metal-backed UI renderer를 editor default로 승격.

## Latest Verification

- 실행 브랜치: `opt/one-shot-quality-speed-20260521-0228`
- Macau fast repeat10:
  - artifact: `output/manual_verification/latest/idea_full_execute_20260521-rerun/macau_fast_repeat10/repeat_summary.json`
  - pipeline avg/min/max: `7.572s / 7.427s / 7.849s`
  - final segment count: `5/5/5` 유지
  - stage trim executed avg: `6.0`
- X5 modes repeat10 quality gate:
  - artifact: `output/manual_verification/latest/idea_full_execute_20260521-rerun/x5_modes_repeat10_current/repeat_summary.md`
  - `mode_high_piecewise_drift`: gate `10/10`, avg `43.693s`, p95 `44.338s`, quality `72.989`, readability `94.568`, timing MAE `0.6455`, final segments `24`
  - `mode_fast`: gate `0/10`, avg `10.250s`, p95 `11.410s`, quality `71.514`, readability `93.057`, timing MAE `0.7347`, final segments `17`
- Tinyping long high:
  - artifact: `output/manual_verification/latest/idea_full_execute_20260521-rerun/tinyping_long_high/tinyping_full_verify.json`
  - media length `24:10`, total `602.634s`, pipeline `574.298s`, peak RSS `4205363200`, final/raw `385/424`, rollback `0`
  - pressure stage는 run 전후 snapshot에서 `critical`을 기록했으므로 장시간 high 작업의 memory pressure는 계속 관찰 대상이다.
- Official QA:
  - `quick`: pass, `output/manual_verification/latest/qa_suite_quick_20260521_121518`
  - `major`: pass, `output/manual_verification/latest/qa_suite_major_20260521_121601`
  - `full`: pass, `output/manual_verification/latest/qa_suite_full_20260521_121658`
  - full Tinyping 60s: fast `22.159s/9.659s final/raw 18/15`, auto `43.083s/9.772s final/raw 18/15`, high `18.837s/18.743s final/raw 16/16`

## Parked Candidates

다음 항목은 현재 active queue가 아니라 별도 실험 후보이다. 실행하려면 새 품질 gate와 rollback branch를 먼저 만든다.

- Quarter-overlap STT/LLM execution: quarter 1 STT가 끝나면 quarter 2 STT와 quarter 1 LLM cleanup/rerank를 겹치는 후보. 최종 commit barrier, X5/Tinyping 품질 gate, segment count 회복 조건 전까지 default 금지.
- Playhead-only dirty-rect repaint: 현재 single-owner 2D full-canvas repaint가 잔상을 막는다. Macau visual smoke로 잔상 없음이 증명될 때만 별도 실험.
- Larger real-index Swift/native policy helper: corrected 500-doc synthetic에서 parity는 통과했지만 speedup이 `< 1.0`이다. 큰 payload에서 새 speedup 근거가 나오기 전까지 Python 유지.

## Waste And Lessons

- 폐기 후보 상세: `waste_action_item.md`
- 반복 금지 교훈: `lesson_n_learned.md`
- 공식 테스트 결과: `test_result.md`
- action/native pointer: `ACTION_ITEMS.md`, `NATIVE_LIB_PLAN.md`
