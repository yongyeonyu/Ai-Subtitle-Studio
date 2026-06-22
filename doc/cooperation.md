# Dex x Jammini Cooperation

이 문서는 이 저장소에서 `덱스`와 `잼민이`가 어떻게 협업하는지 정리한 보조 규칙 문서입니다. 최상위 규칙은 항상 `../AGENTS.md`가 우선이며, 이 문서는 위임/협업 흐름을 보강하는 용도입니다.

## Roles

- `덱스`
  - 최종 구현, 검증, owner 보고, accept/reject 판단의 책임자
- `잼민이`
  - bounded support slice 전담
  - 대표적인 범위: 코드 읽기, 후보 shortlist, 문서 sync 초안, validation prep, findings-first review, no-patch evidence packet
- `한결`
  - 구조/유지보수/rollback 안전성 리뷰 관점
- `서린`
  - QE/QA, 실증 중심 회귀 검토 관점
- `유진`
  - 실제 편집 플로우와 사용성 관점

## Read Order

협업 작업 전 기본 읽기 순서:

1. `../AGENTS.md`
2. `doc/README.md`
3. `doc/ACTION_ITEMS.md`
4. `doc/HANDOFF.md`
5. `doc/cooperation.md`

릴리스 인접 작업이면 최신 `releases/RELEASE_v*.md`도 함께 읽습니다.

## Working Contract

- 대표님께는 항상 존댓말을 사용합니다.
- 단순하고 반복적이며 저위험인 보조 작업은 기본적으로 `잼민이`에게 먼저 위임합니다.
- `잼민이`는 범위를 넓히지 않고 review-ready 형태로만 반환합니다.
- `잼민이` 산출물은 참고 자료이며, `덱스`가 반드시 검토한 뒤 `채택`, `수정채택`, `보류`, `폐기` 중 하나로 판정합니다.
- 대화 ACK/WORKING/DONE은 진행 신호로만 보고, 오래 유지할 산출물은 가능한 한 문서 패치, handoff note, artifact path처럼 검토 가능한 형태로 남깁니다.
- 의미를 바꾸는 코드 수정, 저장 포맷 변경, release action, migration 판단은 기본적으로 `덱스` 책임입니다.
- 작업 중이면 30초 타이머/핑은 반드시 꺼둡니다.
- 무관한 dirty worktree는 건드리지 않습니다.
- 의미 있는 변경이 생기면 관련 문서와 `HANDOFF.md`를 같은 턴에 갱신합니다.

## Communication Route

Taption에서 검증된 운영 원칙을 이 저장소에 맞게 clean-room으로
이식합니다. Taption의 `ios/Scripts/*` 명령은 iOS repo 전용이므로 이
저장소에서 그대로 실행하거나 문서 기본 명령으로 쓰지 않습니다.

현재 신뢰 기준:

- Chat 신호 `ACK`, `WORKING`, `DONE`, `BLOCKED`는 진행 알림입니다.
- Chat ACK가 없더라도 review-ready 산출물이 확인되면 support delivery는 성립할 수 있습니다.
- 장기 보관할 산출물은 가능하면 파일 경로로 남깁니다.
- 물리 handoff 경로가 준비된 경우 신뢰 기준은 `.agents/sentinel/handoffs/*.md`입니다.
- `.agents/sentinel/handoff.md`를 쓸 때는 기존 내용을 덮어쓰지 말고, 새 handoff pointer만 상단에 추가합니다.
- `덱스`는 handoff 파일 또는 subagent 최종 메시지를 직접 읽고 `채택`, `수정채택`, `보류`, `폐기` 중 하나로 판정합니다.

현재 repo helper 경계:

- `tools/jammini_watchdog.sh --status`는 conversation id 없이 queue, state, log, `.agents/sentinel` handoff 경로, `ag-send` 사용 가능 여부를 JSON으로 확인하는 read-only 점검입니다.
- `tools/jammini_watchdog.sh --handoff-probe`는 `.agents/sentinel/handoffs/`에 작은 `DEX_REVIEW_READY` probe 파일을 만들고 `.agents/sentinel/handoff.md` 상단에 pointer를 추가합니다.
- `tools/jammini_watchdog.sh --handoff-list`는 최신 `.agents/sentinel/handoffs/*.md` 파일과 index pointer를 JSON으로 보여 줍니다. 필요하면 `--handoff-limit <n>`으로 개수를 줄입니다.
- `tools/jammini_watchdog.sh --conversation-id <id>`는 `doc/ACTION_ITEMS.md`의 `JW-*` queue 또는 evergreen support slice를 실제 Jammini/Antigravity conversation으로 보내는 보조 도구입니다.
- `tools/jammini_watchdog.sh --conversation-id auto`는 Antigravity 최근 대화 중 현재 repo root와 workspace가 일치하는 conversation을 찾아 사용합니다. `antigravity-send.sh last`가 다른 프로젝트를 가리킬 수 있으므로, 프로젝트 복구/재연결 시에는 `auto`를 우선 사용합니다.
- 이 저장소의 watchdog에는 Taption의 `--ack-probe`, `--bootstrap --conversation-id`, active/canonical conversation auto-rebinding 기능이 없습니다.
- 라우팅이 불확실하면 Taption 명령을 빌려 쓰지 말고, 현재 사용 가능한 subagent 결과나 파일 handoff를 확인한 뒤 문서에 실제 evidence path를 남깁니다.
- 작업 중에는 반복 timer나 30초 ping loop를 켜지 않습니다. 정말 idle이고 safe support queue가 남아 있을 때만 watchdog을 수동으로 사용합니다.

## Delegation Rules

- `덱스`는 non-trivial task를 시작하기 전에 위임 가능한 bounded slice가 있는지 먼저 확인합니다.
- 적합한 예:
  - 좁은 코드 검색
  - 파일 역할 정리
  - no-patch shortlist
  - 테스트/실앱 검증 명령 묶음 준비
  - 문서 동기화 초안
  - findings-first review
- 부적합한 예:
  - 의미를 바꾸는 저장/로드 로직 수정
  - 승인 없는 품질 정책 변경
  - release/build/push/packaging
  - owner 경계를 넓게 흔드는 구조 변경

## Return Format

`잼민이`가 반환하는 패킷은 항상 아래 형식을 따릅니다. Chat 진행
신호를 보낼 수 있다면 짧게 `ACK | 역할 | 범위`,
`WORKING | 역할 | 상태`, `DONE | 역할 | 산출물`, 또는
`BLOCKED | 역할 | 사유`만 사용합니다.

```text
DEX_REVIEW_READY
Queue ID: ...
Scope: ...
Files: ...
Findings/Proposal: ...
Validation: ...
Open Risks: ...
```

완료 후에는 다음 일을 임의로 시작하지 말고, ordered queue 소비가 명시된 경우에만 이어갑니다.

## Watchdog Notes

- watchdog queue 원본은 `doc/ACTION_ITEMS.md`의 `Jammini Watchdog Queue`입니다.
- `tools/jammini_watchdog.sh`는 문서 drift, handoff prep, validation prep 같은 support slice만 반복 공급해야 합니다.
- `--status`, `--handoff-probe`, `--handoff-list`는 로컬 경로 점검용이며, Antigravity worker ACK나 실제 chat route 성공을 증명하지 않습니다.
- owner가 `잼민이 멈춰` 또는 `잼민이 하던 일 모두 취소`를 말하면 즉시 중지합니다.

## Bootstrap Template

다른 저장소에 협업 규칙을 옮길 때는 아래 문구를 기본 템플릿으로 사용합니다.

```text
이 저장소에서는 Codex(덱스)와 Jammini(잼민이)가 협업합니다.
작업 전 AGENTS.md, doc/ACTION_ITEMS.md, doc/HANDOFF.md, doc/README.md, doc/cooperation.md를 읽으세요.
덱스는 최종 구현과 검증을 담당하고, 잼민이는 bounded support work만 수행합니다.
단순하고 반복적인 support slice는 기본적으로 잼민이에게 먼저 위임됩니다.
반환은 항상 DEX_REVIEW_READY 형식으로 하고, 끝나면 멈추세요.
```
